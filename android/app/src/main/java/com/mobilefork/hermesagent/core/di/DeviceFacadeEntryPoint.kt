package com.mobilefork.hermesagent.core.di

import com.mobilefork.hermesagent.device.facade.DeviceFacade
import dagger.hilt.EntryPoint
import dagger.hilt.InstallIn
import dagger.hilt.components.SingletonComponent
import javax.inject.Provider

@EntryPoint
@InstallIn(SingletonComponent::class)
interface DeviceFacadeEntryPoint {
    fun deviceFacade(): Provider<DeviceFacade>
}