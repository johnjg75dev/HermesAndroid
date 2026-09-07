package com.mobilefork.hermesagent.core.di

import android.content.Context
import com.mobilefork.hermesagent.device.facade.DeviceFacade
import com.mobilefork.hermesagent.device.facade.impl.AccessibilityFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.AppsFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.CalendarFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.CleanupFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.ClipboardFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.CompositeDeviceFacade
import com.mobilefork.hermesagent.device.facade.impl.FileFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.LogcatFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.NotificationsFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.NotificationsPostFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.ProjectionFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.ResourcesFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.SensorsFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.ShareFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.SttFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.SystemFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.TerminalFacadeImpl
import com.mobilefork.hermesagent.device.facade.impl.TtsFacadeImpl
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DeviceModule {

    @Provides
    @Singleton
    fun provideTerminalFacade(@ApplicationContext context: Context): TerminalFacadeImpl =
        TerminalFacadeImpl(context)

    @Provides
    @Singleton
    fun provideFileFacade(@ApplicationContext context: Context): FileFacadeImpl =
        FileFacadeImpl(context)

    @Provides
    @Singleton
    fun provideSystemFacade(@ApplicationContext context: Context): SystemFacadeImpl =
        SystemFacadeImpl(context)

    @Provides
    @Singleton
    fun provideAccessibilityFacade(@ApplicationContext context: Context): AccessibilityFacadeImpl =
        AccessibilityFacadeImpl(context)

    @Provides
    @Singleton
    fun provideProjectionFacade(@ApplicationContext context: Context): ProjectionFacadeImpl =
        ProjectionFacadeImpl(context)

    @Provides
    @Singleton
    fun provideSensorsFacade(@ApplicationContext context: Context): SensorsFacadeImpl =
        SensorsFacadeImpl(context)

    @Provides
    @Singleton
    fun provideCalendarFacade(@ApplicationContext context: Context): CalendarFacadeImpl =
        CalendarFacadeImpl(context)

    @Provides
    @Singleton
    fun provideLogcatFacade(@ApplicationContext context: Context): LogcatFacadeImpl =
        LogcatFacadeImpl(context)

    @Provides
    @Singleton
    fun provideNotificationsFacade(@ApplicationContext context: Context): NotificationsFacadeImpl =
        NotificationsFacadeImpl(context)

    @Provides
    @Singleton
    fun provideClipboardFacade(@ApplicationContext context: Context): ClipboardFacadeImpl =
        ClipboardFacadeImpl(context)

    @Provides
    @Singleton
    fun provideShareFacade(@ApplicationContext context: Context): ShareFacadeImpl =
        ShareFacadeImpl(context)

    @Provides
    @Singleton
    fun provideTtsFacade(@ApplicationContext context: Context): TtsFacadeImpl =
        TtsFacadeImpl(context)

    @Provides
    @Singleton
    fun provideSttFacade(@ApplicationContext context: Context): SttFacadeImpl =
        SttFacadeImpl(context)

    @Provides
    @Singleton
    fun provideNotificationsPostFacade(@ApplicationContext context: Context): NotificationsPostFacadeImpl =
        NotificationsPostFacadeImpl(context)

    @Provides
    @Singleton
    fun provideAppsFacade(@ApplicationContext context: Context): AppsFacadeImpl =
        AppsFacadeImpl(context)

    @Provides
    @Singleton
    fun provideResourcesFacade(@ApplicationContext context: Context): ResourcesFacadeImpl =
        ResourcesFacadeImpl(context)

    @Provides
    @Singleton
    fun provideCleanupFacade(@ApplicationContext context: Context): CleanupFacadeImpl =
        CleanupFacadeImpl(context)

    // Aggregate facade that delegates to all individual facades
    @Provides
    @Singleton
    fun provideDeviceFacade(
        terminal: TerminalFacadeImpl,
        file: FileFacadeImpl,
        system: SystemFacadeImpl,
        accessibility: AccessibilityFacadeImpl,
        projection: ProjectionFacadeImpl,
        sensors: SensorsFacadeImpl,
        calendar: CalendarFacadeImpl,
        logcat: LogcatFacadeImpl,
        notifications: NotificationsFacadeImpl,
        clipboard: ClipboardFacadeImpl,
        share: ShareFacadeImpl,
        tts: TtsFacadeImpl,
        stt: SttFacadeImpl,
        notificationsPost: NotificationsPostFacadeImpl,
        apps: AppsFacadeImpl,
        resources: ResourcesFacadeImpl,
        cleanup: CleanupFacadeImpl,
    ): DeviceFacade = CompositeDeviceFacade(
        terminal = terminal,
        file = file,
        system = system,
        accessibility = accessibility,
        projection = projection,
        sensors = sensors,
        calendar = calendar,
        logcat = logcat,
        notifications = notifications,
        clipboard = clipboard,
        share = share,
        tts = tts,
        stt = stt,
        notificationsPost = notificationsPost,
        apps = apps,
        resources = resources,
        cleanup = cleanup,
    )
}