package com.mobilefork.hermesagent.ui.shell

import androidx.annotation.DrawableRes
import com.mobilefork.hermesagent.R
import com.mobilefork.hermesagent.ui.i18n.HermesStrings

enum class AppSection(
    @DrawableRes val iconRes: Int,
) {
    Hermes(iconRes = R.drawable.ic_nav_hermes),
    // label = "Accounts"
    Accounts(iconRes = R.drawable.ic_nav_accounts),
    // label = "Provider Portal"
    NousPortal(iconRes = R.drawable.ic_nav_portal),
    Device(iconRes = R.drawable.ic_nav_device),
    Kanban(iconRes = R.drawable.ic_nav_kanban),
    Cron(iconRes = R.drawable.ic_nav_kanban),
    Insights(iconRes = R.drawable.ic_nav_portal),
    Files(iconRes = R.drawable.ic_nav_device),
    Terminal(iconRes = R.drawable.ic_nav_device),
    Developer(iconRes = R.drawable.ic_nav_settings),
    Settings(iconRes = R.drawable.ic_nav_settings);

    fun label(strings: HermesStrings): String {
        return when (this) {
            Hermes -> strings.sectionHermes
            Accounts -> strings.sectionAccounts
            NousPortal -> strings.sectionPortal
            Device -> strings.sectionDevice
            Kanban -> strings.sectionKanban()
            Cron -> strings.sectionCron()
            Insights -> strings.sectionInsights()
            Files -> strings.sectionFiles()
            Developer -> strings.sectionDeveloper()
            Terminal -> strings.sectionTerminal()
            Settings -> strings.sectionSettings
        }
    }

    fun navigationLabel(strings: HermesStrings): String {
        return when (this) {
            Device -> when (strings.language) {
                com.mobilefork.hermesagent.ui.i18n.AppLanguage.SPANISH -> "Equipo"
                com.mobilefork.hermesagent.ui.i18n.AppLanguage.PORTUGUESE -> "Aparelho"
                com.mobilefork.hermesagent.ui.i18n.AppLanguage.FRENCH -> "Appareil"
                else -> label(strings)
            }
            Kanban -> strings.sectionKanban()
            Cron -> strings.sectionCron()
            Insights -> strings.sectionInsights()
            Files -> strings.sectionFiles()
            Terminal -> label(strings)
            else -> label(strings)
        }
    }

    fun title(strings: HermesStrings): String {
        return when (this) {
            Hermes -> strings.sectionHermes
            Accounts -> strings.sectionAccounts
            NousPortal -> strings.portalTitle
            Device -> strings.sectionDevice
            Kanban -> navigationLabel(strings)
            Cron -> navigationLabel(strings)
            Insights -> navigationLabel(strings)
            Files -> navigationLabel(strings)
            Developer -> navigationLabel(strings)
            Terminal -> navigationLabel(strings)
            Settings -> strings.sectionSettings
        }
    }

    fun subtitle(strings: HermesStrings): String {
        return when (this) {
            Hermes -> strings.subtitleHermes
            Accounts -> strings.subtitleAccounts
            NousPortal -> strings.subtitlePortal
            Device -> strings.subtitleDevice
            Kanban -> strings.subtitleKanban()
            Cron -> strings.subtitleCron()
            Insights -> strings.subtitleInsights()
            Files -> strings.subtitleFiles()
            Developer -> strings.subtitleDeveloper()
            Terminal -> strings.subtitleTerminal()
            Settings -> strings.subtitleSettings
        }
    }
}

data class ShellActionItem(
    val label: String,
    val description: String = "",
    @DrawableRes val iconRes: Int,
    val onClick: () -> Unit,
)
