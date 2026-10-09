package com.ai.teleprompter

import android.app.Application

class App : Application() {
    lateinit var state: TeleprompterState
        private set

    override fun onCreate() {
        super.onCreate()
        state = TeleprompterState(this)
    }
}