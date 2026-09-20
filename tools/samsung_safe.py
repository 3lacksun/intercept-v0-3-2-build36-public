#!/usr/bin/env python3
from pathlib import Path

Path("src/app/src/main/java/com/nexarenew/aiconsole/KotlinCommandApp.kt").write_text(r'''package com.nexarenew.aiconsole

import android.app.Application
import android.util.Log
import androidx.work.Configuration
import androidx.work.WorkManager
import com.nexarenew.aiconsole.data.AppDatabase
import com.nexarenew.aiconsole.data.AppRepository
import com.nexarenew.aiconsole.network.ProviderClient
import com.nexarenew.aiconsole.security.SecureKeyStore
import com.nexarenew.aiconsole.security.PinManager
import com.nexarenew.aiconsole.settings.AppPreferences
import com.nexarenew.aiconsole.tasks.ConnectivityRetryObserver
import java.io.File

class KotlinCommandApp : Application(), Configuration.Provider {
    lateinit var repository: AppRepository
        private set
    lateinit var pinManager: PinManager
        private set
    lateinit var preferences: AppPreferences
        private set
    private var connectivityRetryObserver: ConnectivityRetryObserver? = null

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder().setMinimumLoggingLevel(Log.ERROR).build()

    override fun onCreate() {
        super.onCreate()
        val db = AppDatabase(this)
        runCatching { db.writableDatabase }.onFailure {
            Log.e("INTERCEPT", "Database open/heal failed", it)
        }
        val keys = SecureKeyStore(this)
        repository = AppRepository(db, keys, ProviderClient())
        runCatching { repository.retireLegacyAuxiliaryCredentials() }
        pinManager = PinManager(this, keys)
        preferences = AppPreferences(this)
        connectivityRetryObserver = ConnectivityRetryObserver(this)
        runCatching {
            Class.forName("com.tom_roush.pdfbox.android.PDFBoxResourceLoader")
                .getMethod("init", android.content.Context::class.java)
                .invoke(null, this)
        }.onFailure { Log.w("INTERCEPT", "PDFBox init skipped", it) }
    }

    fun ensureWorkManager() {
        val started = runCatching { WorkManager.getInstance(this); true }.getOrDefault(false)
        if (started) return
        deleteWorkManagerStore()
        runCatching { WorkManager.initialize(this, workManagerConfiguration) }
            .onFailure { Log.e("INTERCEPT", "WorkManager init skipped", it) }
    }

    private fun deleteWorkManagerStore() {
        runCatching { deleteDatabase("androidx.work.workdb") }
        listOf(
            getDatabasePath("androidx.work.workdb"),
            File(noBackupFilesDir, "androidx.work.workdb"),
            File(filesDir, "androidx.work.workdb"),
        ).forEach { root ->
            runCatching {
                root.delete()
                File(root.path + "-wal").delete()
                File(root.path + "-shm").delete()
                File(root.path + "-journal").delete()
            }
        }
    }
}
''')

Path("src/app/src/main/res/values/themes.xml").write_text('''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.Intercept.Base" parent="android:style/Theme.DeviceDefault.Light.NoActionBar">
        <item name="android:windowBackground">@color/stone_lab_white</item>
        <item name="android:statusBarColor">@color/stone_lab_white</item>
        <item name="android:navigationBarColor">@color/stone_lab_white</item>
        <item name="android:windowLightStatusBar">true</item>
    </style>
    <style name="Theme.Intercept" parent="Theme.Intercept.Base" />
</resources>
''')

v31 = Path("src/app/src/main/res/values-v31/themes.xml")
if v31.exists():
    v31.write_text('''<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="Theme.Intercept" parent="Theme.Intercept.Base">
        <item name="android:windowSplashScreenBackground">@color/stone_lab_white</item>
        <item name="android:windowSplashScreenIconBackgroundColor">@color/stone_lab_white</item>
    </style>
</resources>
''')

Path("src/app/src/main/res/drawable/intercept_launch_background.xml").write_text('''<?xml version="1.0" encoding="utf-8"?>
<layer-list xmlns:android="http://schemas.android.com/apk/res/android">
    <item android:drawable="@color/stone_lab_white" />
</layer-list>
''')

fg = Path("src/app/src/main/res/drawable/ic_launcher_foreground.xml")
dst = Path("src/app/src/main/res/drawable/ic_intercept_foreground.xml")
if fg.exists() and not dst.exists():
    dst.write_text(fg.read_text())

main_path = Path("src/app/src/main/java/com/nexarenew/aiconsole/MainActivity.kt")
if main_path.exists():
    main = main_path.read_text()
    main = main.replace("painterResource(R.mipmap.ic_launcher)", "painterResource(R.drawable.ic_launcher_foreground)")
    main = main.replace("painterResource(R.drawable.ic_intercept_foreground)", "painterResource(R.drawable.ic_launcher_foreground)")
    main_path.write_text(main)

observer = Path("src/app/src/main/java/com/nexarenew/aiconsole/tasks/ConnectivityRetryObserver.kt")
if observer.exists():
    text = observer.read_text()
    text = text.replace(
        "override fun onAvailable(network: Network) { OutboxRetryWorker.retryNow(context) }",
        "override fun onAvailable(network: Network) { runCatching { OutboxRetryWorker.retryNow(context) } }",
    )
    observer.write_text(text)

worker_path = Path("src/app/src/main/java/com/nexarenew/aiconsole/tasks/OutboxRetryWorker.kt")
if worker_path.exists():
    worker = worker_path.read_text()
    worker = worker.replace("inputData.getBoolean(KEY_EXPLICIT)", "inputData.getBoolean(KEY_EXPLICIT, false)")
    worker_path.write_text(worker)

manifest_path = Path("src/app/src/main/AndroidManifest.xml")
manifest = manifest_path.read_text()
if "xmlns:tools=" not in manifest:
    manifest = manifest.replace(
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android">',
        '<manifest xmlns:android="http://schemas.android.com/apk/res/android"\n    xmlns:tools="http://schemas.android.com/tools">',
        1,
    )
block = '''
        <provider
            android:name="androidx.startup.InitializationProvider"
            android:authorities="${applicationId}.androidx-startup"
            android:exported="false"
            tools:node="merge">
            <meta-data
                android:name="androidx.work.WorkManagerInitializer"
                android:value="androidx.startup"
                tools:node="remove" />
        </provider>
'''
if "WorkManagerInitializer" not in manifest:
    manifest = manifest.replace("</application>", block + "    </application>", 1)
manifest_path.write_text(manifest)
print("samsung-safe boot overlays applied")
