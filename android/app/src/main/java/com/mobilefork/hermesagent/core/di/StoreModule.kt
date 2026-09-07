package com.mobilefork.hermesagent.core.di

import android.content.Context
import com.mobilefork.hermesagent.data.AppSettingsStore
import com.mobilefork.hermesagent.data.ConversationStore
import com.mobilefork.hermesagent.data.SecureSecretsStore
import com.mobilefork.hermesagent.profile.ProfileManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object StoreModule {

    @Provides
    @Singleton
    fun provideAppSettingsStore(@ApplicationContext context: Context): AppSettingsStore =
        AppSettingsStore(context)

    @Provides
    @Singleton
    fun provideSecureSecretsStore(@ApplicationContext context: Context): SecureSecretsStore =
        SecureSecretsStore(context)

    @Provides
    @Singleton
    fun provideConversationStore(@ApplicationContext context: Context): ConversationStore =
        ConversationStore(context)

    @Provides
    @Singleton
    fun provideProfileManager(): ProfileManager = ProfileManager()
}
