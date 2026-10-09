package com.ai.teleprompter

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.text.BasicTextField
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.collectAsState
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.ai.teleprompter.align.ScriptAligner
import kotlinx.coroutines.delay

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val state = (application as App).state
        // 支持从 Intent extra 注入稿件（用于自动化测试 / 外部启动）
        intent?.getStringExtra("script_text")?.let { state.setScript(it) }
        setContent {
            MaterialTheme(colorScheme = darkColorScheme()) {
                Surface(color = Color.Black, modifier = Modifier.fillMaxSize()) {
                    TeleprompterScreen(state)
                }
            }
        }
    }
}

@Composable
fun TeleprompterScreen(state: TeleprompterState) {
    val isRunning by state.isRunning.collectAsState()
    val asrText by state.asrText.collectAsState()
    val currentIndex by state.currentIndex.collectAsState()
    val scriptText by state.scriptText.collectAsState()
    val status by state.status.collectAsState()

    // 每 150ms 拉一次 ASR 结果
    LaunchedEffect(isRunning) {
        while (isRunning) {
            state.pollAsrTick()
            delay(150)
        }
    }

    var editorText by remember { mutableStateOf("") }
    LaunchedEffect(scriptText) { editorText = scriptText }

    Column(modifier = Modifier.fillMaxSize().padding(12.dp)) {
        // 稿件编辑区
        Text("稿件", style = TextStyle(color = Color.White, fontSize = 14.sp, fontWeight = FontWeight.Bold))
        Spacer(Modifier.height(4.dp))
        BasicTextField(
            value = editorText,
            onValueChange = {
                editorText = it
                state.setScript(it)
            },
            textStyle = TextStyle(color = Color.White, fontSize = 14.sp),
            modifier = Modifier
                .fillMaxWidth()
                .height(120.dp)
                .background(Color(0xFF101010))
                .padding(8.dp)
        )

        Spacer(Modifier.height(8.dp))

        // 当前 ASR 识别文本
        Text("ASR: $asrText", style = TextStyle(color = Color(0xFF80FF80), fontSize = 12.sp))
        Text(
            "cursor: $currentIndex / ${state.scriptText.value.length} 字",
            style = TextStyle(color = Color(0xFF80FF80), fontSize = 12.sp)
        )
        Text("status: $status", style = TextStyle(color = Color.Gray, fontSize = 12.sp))

        Spacer(Modifier.height(8.dp))

        // 当前提词视图：已读 + 当前 + 未读
        if (scriptText.isNotBlank()) {
            val cursor = currentIndex
            val tokens = remember(scriptText) { ScriptAligner.normalize(scriptText) }
            val spoken = if (cursor < 0) "" else tokens.take(cursor + 1).joinToString("")
            val current = if (cursor < 0 || cursor >= tokens.size - 1) "" else tokens.getOrNull(cursor + 1) ?: ""
            val upcoming = if (cursor < 0) tokens.joinToString("") else tokens.drop(cursor + 2).joinToString("")

            Column(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .verticalScroll(rememberScrollState())
                    .background(Color(0xFF050505))
                    .padding(16.dp)
            ) {
                Text(spoken, style = TextStyle(color = Color(0xFF606060), fontSize = 28.sp, lineHeight = 40.sp))
                if (current.isNotEmpty()) {
                    Text(
                        current,
                        style = TextStyle(
                            color = Color(0xFFFFD600),
                            fontSize = 32.sp,
                            fontWeight = FontWeight.Bold,
                            lineHeight = 44.sp,
                        )
                    )
                }
                Text(upcoming, style = TextStyle(color = Color.White, fontSize = 28.sp, lineHeight = 40.sp))
            }
        } else {
            Box(
                modifier = Modifier
                    .weight(1f)
                    .fillMaxWidth()
                    .background(Color(0xFF050505)),
                contentAlignment = Alignment.Center
            ) {
                Text("请先在下方粘贴你的直播稿", style = TextStyle(color = Color.Gray))
            }
        }

        Spacer(Modifier.height(8.dp))

        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
            Button(
                onClick = { state.toggleRecording() },
                modifier = Modifier.weight(1f),
                colors = ButtonDefaults.buttonColors(
                    containerColor = if (isRunning) Color.Red else Color(0xFF1976D2)
                )
            ) {
                Text(if (isRunning) "停止" else "开始识别")
            }
        }
    }
}