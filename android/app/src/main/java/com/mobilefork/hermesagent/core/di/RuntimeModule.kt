package com.mobilefork.hermesagent.core.di

import android.content.Context
import com.chaquo.python.Python
import com.chaquo.python.android.AndroidPlatform
import com.mobilefork.hermesagent.backend.HermesRuntimeManager
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object RuntimeModule {

    @Provides
    @Singleton
    fun providePythonRuntime(@ApplicationContext context: Context): Python {
        if (!Python.isStarted()) {
            Python.start(AndroidPlatform(context))
        }
        return Python.getInstance()
    }

    @Provides
    @Singleton
    fun provideHermesRuntimeManager(): HermesRuntimeManager = HermesRuntimeManager
}