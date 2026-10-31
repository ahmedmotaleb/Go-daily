package com.godaily.driver

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.repeatOnLifecycle
import com.godaily.driver.ui.MainViewModel
import com.godaily.driver.ui.Screen
import com.godaily.driver.ui.screens.HomeScreen
import com.godaily.driver.ui.screens.LoginScreen
import com.godaily.driver.ui.screens.PermissionScreen
import com.godaily.driver.ui.theme.GoDailyTheme
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {
    private val vm: MainViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        lifecycleScope.launch {
            // Keep the tracking card current while the app is on screen.
            repeatOnLifecycle(Lifecycle.State.STARTED) {
                while (true) {
                    vm.checkTracking()
                    delay(5_000)
                }
            }
        }
        setContent {
            GoDailyTheme {
                val state by vm.state.collectAsStateWithLifecycle()
                Surface(color = MaterialTheme.colorScheme.background, modifier = Modifier.fillMaxSize()) {
                    when (state.screen) {
                        Screen.LOADING -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                        Screen.LOGIN -> LoginScreen(state.busy, state.loginError, vm::login)
                        Screen.HOME -> if (state.showPermissions) {
                            PermissionScreen(
                                onAcceptDisclosure = vm::acceptDisclosure,
                                onFinished = vm::permissionsUpdated,
                                onCancel = { vm.showPermissions(false) },
                            )
                        } else {
                            HomeScreen(state, vm)
                        }
                    }
                }
            }
        }
    }

    override fun onResume() {
        super.onResume()
        // Permissions or settings may have changed while the app was away.
        vm.checkTracking()
    }
}
