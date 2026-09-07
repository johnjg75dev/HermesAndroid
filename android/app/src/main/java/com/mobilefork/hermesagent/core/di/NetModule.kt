package com.mobilefork.hermesagent.core.di

import android.content.Context
import com.mobilefork.hermesagent.api.HermesApiClient
import com.mobilefork.hermesagent.api.HermesSseClient
import com.mobilefork.hermesagent.data.HermesNetworkPolicy
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object NetModule {

    @Provides
    @Singleton
    fun provideOkHttpClient(): OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(10, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.MINUTES)
        .build()

    @Provides
    @Singleton
    fun provideHermesApiClient(
        @ApplicationContext context: Context,
        okHttpClient: OkHttpClient,
    ): HermesApiClient = HermesApiClient(
        baseUrl = "", // Set at runtime
        apiKey = null,
        httpClient = okHttpClient,
        networkGuard = { url ->
            HermesNetworkPolicy.requireExternalNetworkAllowed(
                context.applicationContext,
                url,
                actionLabel = "chat request",
            )
        },
    )

    @Provides
    @Singleton
    fun provideHermesSseClient(
        @ApplicationContext context: Context,
        okHttpClient: OkHttpClient,
    ): HermesSseClient = HermesSseClient(
        baseUrl = "", // Set at runtime
        apiKey = null,
        networkGuard = { url ->
            HermesNetworkPolicy.requireExternalNetworkAllowed(
                context.applicationContext,
                url,
                actionLabel = "SSE stream",
            )
        },
    )
}
