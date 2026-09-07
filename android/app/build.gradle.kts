import java.util.Properties
import java.io.ByteArrayOutputStream

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
    id("com.google.dagger.hilt.android")
    id("com.google.devtools.ksp")
}

val repoRoot = rootDir.parentFile
val hermesVersionFile = repoRoot.resolve("hermes_cli/__init__.py")
val releaseTag = "v0.13.147"
val hermesSourceDigest = System.getenv("HERMES_SOURCE_DIGEST")
    .orEmpty()
    .trim()
    .lowercase()
    .also { digest ->
        require(digest.isBlank() || Regex("[0-9a-f]{64}").matches(digest)) {
            "HERMES_SOURCE_DIGEST must be one lowercase SHA-256 digest, got '$digest'"
        }
    }
val generatedPythonBuildLibDir = repoRoot.resolve("build/lib")
val hermesWheelDir = layout.buildDirectory.dir("hermes-wheel")
val hermesAndroidPackageDir = repoRoot.resolve("hermes_android")
val hermesAndroidPyproject = hermesAndroidPackageDir.resolve("pyproject.toml")
fun hermesAndroidVersion(): String =
    Regex("""(?m)^version\s*=\s*"([^"]+)"""").find(hermesAndroidPyproject.readText())?.groupValues?.get(1)
        ?: throw GradleException("Cannot read project.version from ${hermesAndroidPyproject.path}")
fun hermesAndroidWheelName(): String = "hermes_android-${hermesAndroidVersion()}-py3-none-any.whl"
val hermesAndroidWheelDir = layout.buildDirectory.dir("hermes-android-wheel")
val generatedHermesLinuxAssetsDir = layout.buildDirectory.dir("generated/hermes-linux-assets")
val generatedHermesNativeLibsDir = layout.buildDirectory.dir("generated/hermes-native-libs")
val hermesLinuxAssetLockFile = repoRoot.resolve("hermes_android/termux_linux_assets.lock.json")
val skipHermesAndroidLinuxAssets = providers.gradleProperty("skipHermesAndroidLinuxAssets")
    .map { it.equals("true", ignoreCase = true) }
    .getOrElse(false)
val keystorePropertiesFile = rootDir.resolve("keystore.properties")
val keystoreProperties = Properties().apply {
    if (keystorePropertiesFile.isFile) {
        keystorePropertiesFile.inputStream().use(::load)
    }
}
val hasReleaseKeystore = keystoreProperties.isNotEmpty()
val liteRtLmStableVersion = "0.16.0"
val liteRtLmVersion = providers.gradleProperty("hermesLiteRtLmVersion")
    .getOrElse(liteRtLmStableVersion)
    .trim()
    .also { version ->
        require(Regex("""\d+\.\d+\.\d+(?:[-.][0-9A-Za-z.]+)?""").matches(version)) {
            "hermesLiteRtLmVersion must be one exact LiteRT-LM version, got '$version'"
        }
    }
val liteRtLmLocalAar = providers.gradleProperty("hermesLiteRtLmLocalAar")
    .orNull
    ?.trim()
    ?.takeIf { it.isNotEmpty() }
    ?.let { path ->
        val candidate = file(path)
        require(candidate.isFile && candidate.extension.equals("aar", ignoreCase = true)) {
            "hermesLiteRtLmLocalAar must point to an existing .aar file, got '$path'"
        }
        candidate
    }

fun hermesVersionName(): String {
    val text = hermesVersionFile.readText()
    val match = Regex("""__version__\s*=\s*\"([^\"]+)\"""").find(text)
    return match?.groupValues?.get(1) ?: "0.1.0"
}

fun androidVersionName(): String {
    if (releaseTag.isBlank()) {
        return hermesVersionName()
    }
    val semverMatch = Regex("""v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.-]+))?""").matchEntire(releaseTag)
    if (semverMatch != null) {
        return releaseTag.removePrefix("v")
    }
    return hermesVersionName()
}

fun semverVersionCode(versionText: String): Int? {
    val semverMatch = Regex("""v?(\d+)\.(\d+)\.(\d+)(?:-([A-Za-z]+)(?:[.-]?(\d+))?)?""").matchEntire(versionText)
    if (semverMatch != null) {
        val major = semverMatch.groupValues[1].toInt()
        val minor = semverMatch.groupValues[2].toInt()
        val patch = semverMatch.groupValues[3].toInt()
        val prerelease = semverMatch.groupValues[4].lowercase()
        val prereleaseSeq = semverMatch.groupValues[5].ifBlank { "0" }.toInt().coerceIn(0, 9)
        val prereleaseRank = when (prerelease) {
            "alpha" -> 1
            "beta" -> 2
            "rc" -> 3
            "" -> 9
            else -> 4
        }
        return (major * 1_000_000) + (minor * 10_000) + (patch * 100) + (prereleaseRank * 10) + prereleaseSeq
    }
    return null
}

fun hermesVersionCode(): Int {
    if (releaseTag.isBlank()) {
        return semverVersionCode(hermesVersionName()) ?: 1
    }

    semverVersionCode(releaseTag)?.let { return it }

    val releaseMatch = Regex("""v(\d{4})\.(\d{1,2})\.(\d{1,2})(?:\.(\d{1,2}))?""").matchEntire(releaseTag)
        ?: return 1
    val year = releaseMatch.groupValues[1]
    val month = releaseMatch.groupValues[2].padStart(2, '0')
    val day = releaseMatch.groupValues[3].padStart(2, '0')
    val seq = releaseMatch.groupValues[4].ifBlank { "0" }.padStart(2, '0')
    return "$year$month$day$seq".toInt()
}

fun resolvedBuildPython(): String {
    val configured = System.getenv("PYTHON_FOR_BUILD").orEmpty().trim()
    if (configured.isNotBlank()) {
        return configured
    }
    val osName = System.getProperty("os.name").lowercase()
    return if (osName.contains("windows")) "python" else "python3.13"
}

fun hermesWheelName(): String = "hermes_agent-${hermesVersionName()}-py3-none-any.whl"

if (hermesSourceDigest.isNotBlank()) {
    require(liteRtLmLocalAar == null) {
        "A source-bound release-evidence build cannot use hermesLiteRtLmLocalAar"
    }
    require(liteRtLmVersion == liteRtLmStableVersion) {
        "A source-bound release-evidence build must use the release LiteRT-LM version " +
            "$liteRtLmStableVersion, got $liteRtLmVersion"
    }
    val identityOutput = providers.exec {
        commandLine(
            resolvedBuildPython(),
            repoRoot.resolve("scripts/android_release_evidence.py").absolutePath,
            "source-identity",
            "--repo-root",
            repoRoot.absolutePath,
            "--require-clean",
        )
    }.standardOutput.asText.get()
    val actualSourceDigest = identityOutput
        .lineSequence()
        .singleOrNull { it.startsWith("sourceDigest=") }
        ?.substringAfter('=')
        .orEmpty()
    require(actualSourceDigest == hermesSourceDigest) {
        "HERMES_SOURCE_DIGEST does not match the clean committed source: " +
            "expected $actualSourceDigest, got $hermesSourceDigest"
    }
}

android {
    namespace = "com.mobilefork.hermesagent"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.mobilefork.hermesagent"
        minSdk = 24
        targetSdk = 36
        versionCode = hermesVersionCode()
        versionName = androidVersionName()
        buildConfigField(
            "String",
            "HERMES_SOURCE_DIGEST",
            "\"unbound\"",
        )
        buildConfigField(
            "String",
            "HERMES_LITERTLM_COORDINATE",
            "\"com.google.ai.edge.litertlm:litertlm-android:$liteRtLmVersion\"",
        )
        buildConfigField(
            "boolean",
            "HERMES_LITERTLM_LOCAL_AAR",
            (liteRtLmLocalAar != null).toString(),
        )
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        vectorDrawables {
            useSupportLibrary = true
        }
        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    splits {
        abi {
            isEnable = false
            reset()
            include("arm64-v8a", "x86_64")
            isUniversalApk = true
        }
    }

    dependenciesInfo {
        includeInApk = false
        includeInBundle = false
    }


    buildTypes {
        debug {
            buildConfigField(
                "String",
                "HERMES_SOURCE_DIGEST",
                "\"${hermesSourceDigest.ifBlank { "unbound" }}\"",
            )
        }
        release {
            if (hasReleaseKeystore) {
            }
            isMinifyEnabled = false
            isShrinkResources = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro"
            )
        }
        create("benchmark") {
            initWith(getByName("release"))
            matchingFallbacks += listOf("release")
            isDebuggable = false
            buildConfigField(
                "String",
                "HERMES_SOURCE_DIGEST",
                "\"${hermesSourceDigest.ifBlank { "unbound" }}\"",
            )
            manifestPlaceholders["hermesBenchmarkSourceDigest"] =
                hermesSourceDigest.ifBlank { "unbound" }
            manifestPlaceholders["hermesBenchmarkVersionName"] = androidVersionName()
            manifestPlaceholders["hermesBenchmarkVersionCode"] = hermesVersionCode().toString()
            manifestPlaceholders["hermesBenchmarkLiteRtLmCoordinate"] =
                "com.google.ai.edge.litertlm:litertlm-android:$liteRtLmVersion"
        }
    }

    testOptions {
        unitTests {
            isIncludeAndroidResources = true
            all { test ->
                test.maxParallelForks = 1
                test.jvmArgs(
                    "--add-opens=java.base/java.io=ALL-UNNAMED",
                    "--add-opens=java.base/java.lang=ALL-UNNAMED",
                    "--add-opens=java.base/java.lang.invoke=ALL-UNNAMED",
                    "--add-opens=java.base/java.lang.reflect=ALL-UNNAMED",
                    "--add-opens=java.base/java.util=ALL-UNNAMED",
                )
                test.testLogging {
                    events("failed", "skipped")
                    exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
                    showCauses = true
                    showExceptions = true
                    showStackTraces = true
                }
            }
        }
    }

    lint {
        baseline = file("lint-baseline.xml")
        abortOnError = true
        checkReleaseBuilds = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        aidl = true
        buildConfig = true
        compose = true
    }

    androidResources {
        ignoreAssetsPattern = "!.svn:!.git:!.ds_store:!*.scc:!CVS:!thumbs.db:!picasa.ini:!*~"
    }

    sourceSets {
        getByName("main") {
            if (!skipHermesAndroidLinuxAssets) {
                assets.srcDirs(generatedHermesLinuxAssetsDir.get().asFile)
                jniLibs.srcDirs(generatedHermesNativeLibsDir.get().asFile)
            }
        }
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
        resources {
            excludes += "/META-INF/{AL2.0,LGPL2.1}"
        }
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

chaquopy {
    defaultConfig {
        version = "3.13"

        buildPython(resolvedBuildPython())

        pip {
            // Install Hermes itself from an isolated wheel, then layer an explicit
            // Android-safe runtime set. Chaquopy applies pip options globally per
            // block, so the runtime requirements file must include all transitive
            // dependencies explicitly.
            options("--no-deps")
            install("../../android/pip-stubs/anthropic-stub")
            install("../../android/pip-stubs/fal-client-stub")
            install("build/hermes-wheel/${hermesWheelName()}")
            install("build/hermes-android-wheel/${hermesAndroidWheelName()}")
            install("-r", "../../requirements-android-chaquopy.txt")
        }
    }
}

val prepareHermesAndroidWheel = tasks.register<Exec>("prepareHermesAndroidWheel") {
    group = "python"
    description = "Build a no-deps Hermes wheel for the Android embedded runtime."
    val wheelDir = hermesWheelDir.get().asFile
    inputs.file(repoRoot.resolve("pyproject.toml"))
    inputs.file(repoRoot.resolve("README.md"))
    listOf(
        "agent",
        "tools",
        "hermes_cli",
        "gateway",
        "tui_gateway",
        "cron",
        "acp_adapter",
        "plugins",
        "providers",
    ).forEach { packageDir ->
        inputs.files(fileTree(repoRoot.resolve(packageDir)) {
            include("**/*.py")
            include("**/*.json")
            include("**/*.yaml")
            include("**/*.yml")
            include("**/*.txt")
            include("**/*.html")
            include("**/*.js")
            include("**/*.css")
        })
    }
    outputs.file(wheelDir.resolve(hermesWheelName()))
    doFirst {
        wheelDir.mkdirs()
        val repoRootPath = repoRoot.canonicalFile.toPath()
        val buildLibPath = generatedPythonBuildLibDir.canonicalFile.toPath()
        check(buildLibPath.startsWith(repoRootPath)) {
            "Refusing to remove Python build output outside repository: $buildLibPath"
        }
        if (generatedPythonBuildLibDir.exists()) {
            generatedPythonBuildLibDir.deleteRecursively()
        }
    }
    commandLine(
        resolvedBuildPython(),
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "--wheel-dir",
        wheelDir.absolutePath,
        repoRoot.absolutePath,
    )
}

val prepareHermesAndroidStandaloneWheel = tasks.register<Exec>("prepareHermesAndroidStandaloneWheel") {
    group = "python"
    description = "Build the standalone hermes-android runtime wheel (src layout)."
    val wheelDir = hermesAndroidWheelDir.get().asFile
    inputs.file(hermesAndroidPyproject)
    inputs.files(fileTree(hermesAndroidPackageDir.resolve("src")) { include("**/*.py") })
    outputs.file(wheelDir.resolve(hermesAndroidWheelName()))
    doFirst {
        wheelDir.mkdirs()
    }
    commandLine(
        resolvedBuildPython(),
        "-m",
        "pip",
        "wheel",
        "--no-deps",
        "--wheel-dir",
        wheelDir.absolutePath,
        hermesAndroidPackageDir.absolutePath,
    )
}

val prepareHermesAndroidLinuxAssets = tasks.register<Exec>("prepareHermesAndroidLinuxAssets") {
    group = "android"
    description = "Download and normalize the Android Linux command-suite assets."
    val outputDir = generatedHermesLinuxAssetsDir.get().asFile
    inputs.file(hermesLinuxAssetLockFile)
    inputs.file(repoRoot.resolve("scripts/prepare_android_linux_assets.py"))
    inputs.file(repoRoot.resolve("hermes_android/src/hermes_android/linux/assets.py"))
    outputs.dir(outputDir)
    doFirst {
        outputDir.mkdirs()
    }
    commandLine(
        resolvedBuildPython(),
        repoRoot.resolve("scripts/prepare_android_linux_assets.py").absolutePath,
        "--output-dir",
        outputDir.absolutePath,
        "--lock-file",
        hermesLinuxAssetLockFile.absolutePath,
    )
}

val prepareHermesAndroidNativeLibs = tasks.register<Exec>("prepareHermesAndroidNativeLibs") {
    group = "android"
    description = "Expose embedded Linux launchers through Android's executable native-library directory."
    dependsOn(prepareHermesAndroidLinuxAssets)
    val outputDir = generatedHermesNativeLibsDir.get().asFile
    inputs.file(repoRoot.resolve("scripts/prepare_android_native_libs.py"))
    inputs.dir(generatedHermesLinuxAssetsDir)
    outputs.dir(outputDir)
    doFirst {
        outputDir.mkdirs()
    }
    commandLine(
        resolvedBuildPython(),
        repoRoot.resolve("scripts/prepare_android_native_libs.py").absolutePath,
        "--linux-assets-dir",
        generatedHermesLinuxAssetsDir.get().asFile.absolutePath,
        "--output-dir",
        outputDir.absolutePath,
    )
}

if (!skipHermesAndroidLinuxAssets) {
    tasks.named("preBuild") {
        dependsOn(prepareHermesAndroidLinuxAssets)
        dependsOn(prepareHermesAndroidNativeLibs)
    }
}

tasks.matching { it.name.endsWith("PythonRequirements") }.configureEach {
    dependsOn(prepareHermesAndroidWheel)
    dependsOn(prepareHermesAndroidStandaloneWheel)
    if (!skipHermesAndroidLinuxAssets) {
        dependsOn(prepareHermesAndroidLinuxAssets)
    }
    val taskName = name
    val variant = taskName.removePrefix("install").removeSuffix("PythonRequirements")
    if (variant.isNotEmpty()) {
        dependsOn("merge${variant}PythonSources")
        dependsOn("merge${variant}NativeDebugMetadata")
        dependsOn("check${variant}AarMetadata")
    }
}

// Chaquopy's Windows installer marks packaged Python directories execute-only.
// Gradle 8.11 cannot fingerprint those generated proxy inputs even though the
// Chaquopy task itself can consume them. Linux/F-Droid builds are unaffected.
tasks.matching {
    it.name.endsWith("PythonProxies") || it.name.endsWith("PythonRequirementsAssets")
}.configureEach {
    doNotTrackState("Chaquopy proxy inputs use execute-only package directories on Windows")
}

fun normalizeChaquopyBuildJson(variant: String) {
    if (variant.isBlank()) {
        return
    }
    val buildJson = layout.buildDirectory.file(
        "python/assets/build/${variant.lowercase()}/chaquopy/build.json"
    ).get().asFile
    if (!buildJson.isFile) {
        return
    }
    providers.exec {
        commandLine(
            resolvedBuildPython(),
            repoRoot.resolve("scripts/normalize_chaquopy_assets.py").absolutePath,
            "build-json",
            buildJson.absolutePath,
        )
    }
}

fun normalizeChaquopyRequirementsImy(variant: String) {
    if (variant.isBlank()) {
        return
    }
    val requirementsImy = layout.buildDirectory.file(
        "python/assets/requirements/${variant.lowercase()}/chaquopy/requirements-common.imy"
    ).get().asFile
    if (!requirementsImy.isFile) {
        return
    }
    providers.exec {
        commandLine(
            resolvedBuildPython(),
            repoRoot.resolve("scripts/normalize_chaquopy_assets.py").absolutePath,
            "requirements-imy",
            requirementsImy.absolutePath,
        )
    }
}

afterEvaluate {
    tasks.matching { it.name.endsWith("PythonRequirementsAssets") }.configureEach {
        inputs.file(repoRoot.resolve("scripts/normalize_chaquopy_assets.py"))
        val taskName = name
        doLast {
            normalizeChaquopyRequirementsImy(
                taskName.removePrefix("generate").removeSuffix("PythonRequirementsAssets")
            )
        }
    }
    tasks.matching { it.name.endsWith("PythonBuildAssets") }.configureEach {
        inputs.file(repoRoot.resolve("scripts/normalize_chaquopy_assets.py"))
        val taskName = name
        doFirst {
            normalizeChaquopyRequirementsImy(
                taskName.removePrefix("generate").removeSuffix("PythonBuildAssets")
            )
        }
        doLast {
            normalizeChaquopyBuildJson(
                taskName.removePrefix("generate").removeSuffix("PythonBuildAssets")
            )
        }
    }
    tasks.matching { it.name.startsWith("merge") && it.name.endsWith("Assets") }.configureEach {
        inputs.file(repoRoot.resolve("scripts/normalize_chaquopy_assets.py"))
        val taskName = name
        doFirst {
            normalizeChaquopyBuildJson(
                taskName.removePrefix("merge").removeSuffix("Assets")
            )
        }
    }
}

dependencies {
    val composeBom = platform("androidx.compose:compose-bom:2024.12.01")

    implementation("androidx.core:core-ktx:1.19.0")
    implementation("dev.rikka.shizuku:api:13.1.5")
    implementation("dev.rikka.shizuku:provider:13.1.5")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.11.0")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.11.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.11.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.11.0")
    implementation("androidx.activity:activity-compose:1.13.0")
    implementation(composeBom)
    androidTestImplementation(composeBom)
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.ui:ui-graphics")
    implementation("androidx.compose.ui:ui-tooling-preview")
    implementation("androidx.compose.material3:material3")
    implementation("androidx.documentfile:documentfile:1.0.1")
    implementation("com.squareup.okhttp3:okhttp:5.5.0")
    implementation("com.squareup.okhttp3:okhttp-sse:5.5.0")
    implementation("org.apache.commons:commons-compress:1.26.2")
    implementation("org.tukaani:xz:1.9")
    implementation("androidx.security:security-crypto:1.1.0")
    implementation("androidx.profileinstaller:profileinstaller:1.4.1")
    implementation("androidx.datastore:datastore-preferences:1.1.7")
    implementation("org.json:json:20240303")
    // Hilt
    implementation("com.google.dagger:hilt-android:2.60.1")
    ksp("com.google.dagger:hilt-compiler:2.60.1")
    implementation("androidx.hilt:hilt-navigation-compose:1.4.0")
    implementation("androidx.hilt:hilt-work:1.4.0")
    // Release/F-Droid builds use the exact stable default (0.16.0). Developers can compile
    // an upstream preview version or a locally built LiteRT-LM main-branch AAR
    // without weakening the reproducible release pin.
    if (liteRtLmLocalAar != null) {
        implementation(files(liteRtLmLocalAar))
    } else {
        implementation("com.google.ai.edge.litertlm:litertlm-android:$liteRtLmVersion")
    }
    implementation("org.nanohttpd:nanohttpd:2.3.1")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.robolectric:robolectric:4.16.1")
    testImplementation("com.squareup.okhttp3:mockwebserver:5.5.0")
    testImplementation("org.json:json:20240303")
    testImplementation("com.google.dagger:hilt-android-testing:2.60.1")
    kspTest("com.google.dagger:hilt-compiler:2.60.1")
    androidTestImplementation("androidx.test:core-ktx:1.6.1")
    androidTestImplementation("androidx.test.ext:junit:1.3.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation("androidx.test.espresso:espresso-intents:3.7.0")
    androidTestImplementation("androidx.compose.ui:ui-test-junit4")
    androidTestImplementation("com.google.dagger:hilt-android-testing:2.60.1")
    kspAndroidTest("com.google.dagger:hilt-compiler:2.60.1")
    debugImplementation("androidx.compose.ui:ui-tooling")
    debugImplementation("androidx.compose.ui:ui-test-manifest")
}
