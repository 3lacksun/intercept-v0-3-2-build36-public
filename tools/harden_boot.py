#!/usr/bin/env python3
from pathlib import Path
import re

db_path = Path("src/app/src/main/java/com/nexarenew/aiconsole/data/AppDatabase.kt")
app_path = Path("src/app/src/main/java/com/nexarenew/aiconsole/KotlinCommandApp.kt")
worker_path = Path("src/app/src/main/java/com/nexarenew/aiconsole/tasks/OutboxRetryWorker.kt")

db = db_path.read_text()
safe_add = """    private fun tableExists(db: SQLiteDatabase, table: String): Boolean =
        db.rawQuery("SELECT name FROM sqlite_master WHERE type='table' AND name=?", arrayOf(table)).use { it.moveToFirst() }

    private fun addColumnIfMissing(db: SQLiteDatabase, table: String, column: String, definition: String) {
        if (!tableExists(db, table)) return
        val exists = db.rawQuery("PRAGMA table_info($table)", null).use { cursor ->
            val nameIndex = cursor.getColumnIndexOrThrow("name")
            var found = false
            while (cursor.moveToNext()) {
                if (cursor.getString(nameIndex).equals(column, ignoreCase = true)) {
                    found = true
                    break
                }
            }
            found
        }
        if (!exists) db.execSQL("ALTER TABLE $table ADD COLUMN $column $definition")
    }"""
db, n = re.subn(
    r"    private fun addColumnIfMissing\(db: SQLiteDatabase, table: String, column: String, definition: String\) \{.*?\n    \}",
    safe_add,
    db,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit(f"addColumnIfMissing replace count={n}")

voice_extra = """
        addColumnIfMissing(db, \"voice_sessions\", \"assistant_message_id\", \"TEXT\")
        addColumnIfMissing(db, \"voice_sessions\", \"request_id\", \"TEXT\")
        addColumnIfMissing(db, \"voice_sessions\", \"capture_active\", \"INTEGER NOT NULL DEFAULT 0\")
        addColumnIfMissing(db, \"voice_sessions\", \"tts_active\", \"INTEGER NOT NULL DEFAULT 0\")
        addColumnIfMissing(db, \"voice_sessions\", \"updated_at\", \"INTEGER NOT NULL DEFAULT 0\")
        addColumnIfMissing(db, \"attachments\", \"original_filename\", \"TEXT NOT NULL DEFAULT ''\")
        addColumnIfMissing(db, \"attachments\", \"mime_type\", \"TEXT NOT NULL DEFAULT ''\")
        addColumnIfMissing(db, \"outbox\", \"recovered_at\", \"INTEGER\")
        addColumnIfMissing(db, \"outbox\", \"recovery_attempts\", \"INTEGER NOT NULL DEFAULT 0\")
"""
needle = 'db.execSQL("CREATE INDEX IF NOT EXISTS idx_voice_session_chat ON voice_sessions(chat_id,updated_at DESC)")'
if 'addColumnIfMissing(db, "voice_sessions", "capture_active"' not in db:
    if needle not in db:
        raise SystemExit("voice session index not found")
    db = db.replace(needle, needle + "\n" + voice_extra, 1)

on_open = """    override fun onOpen(db: SQLiteDatabase) {
        super.onOpen(db)
        runCatching {
            createV2Tables(db); createV3Tables(db); createV4Tables(db); createV5Tables(db)
            createV6Tables(db); createV7Tables(db); createV8Tables(db); createV9Tables(db)
            createV10Tables(db); createV11Tables(db); createV12Tables(db); createV13Tables(db)
            createV14Tables(db); createV15Tables(db); createV16Tables(db); createV17Tables(db)
            createV18Tables(db); createV19Tables(db)
        }
    }

"""
on_downgrade = """    override fun onDowngrade(db: SQLiteDatabase, oldVersion: Int, newVersion: Int) {
        createV19Tables(db)
    }

"""
insert = ""
if "override fun onOpen" not in db:
    insert += on_open
if "override fun onDowngrade" not in db:
    insert += on_downgrade
if insert:
    if "    companion object {" not in db:
        raise SystemExit("companion object marker missing")
    db = db.replace("    companion object {", insert + "    companion object {", 1)

db_path.write_text(db)
text = db_path.read_text()
if "fun onOpen" not in text or "fun onDowngrade" not in text or "tableExists" not in text:
    raise SystemExit("AppDatabase healers not applied")

app_path.write_text(
    """package com.nexarenew.aiconsole

import android.app.Application
import android.util.Log
import com.tom_roush.pdfbox.android.PDFBoxResourceLoader
import com.nexarenew.aiconsole.data.AppDatabase
import com.nexarenew.aiconsole.data.AppRepository
import com.nexarenew.aiconsole.network.ProviderClient
import com.nexarenew.aiconsole.security.SecureKeyStore
import com.nexarenew.aiconsole.security.PinManager
import com.nexarenew.aiconsole.tasks.OutboxRetryWorker
import com.nexarenew.aiconsole.tasks.ConnectivityRetryObserver
import com.nexarenew.aiconsole.tasks.DocumentIndexWorker
import com.nexarenew.aiconsole.settings.AppPreferences
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.flow.first

class KotlinCommandApp : Application() {
    lateinit var repository: AppRepository
        private set
    lateinit var pinManager: PinManager
        private set
    lateinit var preferences: AppPreferences
        private set
    private lateinit var connectivityRetryObserver: ConnectivityRetryObserver

    override fun onCreate() {
        super.onCreate()
        runCatching { PDFBoxResourceLoader.init(this) }.onFailure {
            Log.w("INTERCEPT", "PDFBox init skipped", it)
        }
        val db = AppDatabase(this)
        runCatching { db.writableDatabase }.onFailure {
            Log.e("INTERCEPT", "Database open/heal failed", it)
        }
        val keys = SecureKeyStore(this)
        repository = AppRepository(db, keys, ProviderClient())
        runCatching { repository.retireLegacyAuxiliaryCredentials() }
        pinManager = PinManager(this, keys)
        preferences = AppPreferences(this)
        val automaticBackground = runCatching {
            runBlocking {
                preferences.migrateToUnifiedControls()
                preferences.automaticBackgroundWorkEnabled.first()
            }
        }.getOrDefault(false)
        connectivityRetryObserver = ConnectivityRetryObserver(this)
        if (automaticBackground) {
            runCatching { OutboxRetryWorker.enqueuePeriodic(this) }
            runCatching { DocumentIndexWorker.recoverInterrupted(this, repository) }
            runCatching { connectivityRetryObserver.start() }
        }
    }
}
"""
)

worker = worker_path.read_text()
worker_path.write_text(worker.replace("inputData.getBoolean(KEY_EXPLICIT)", "inputData.getBoolean(KEY_EXPLICIT, false)"))
print("boot-path patches applied")
