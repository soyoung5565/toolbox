package com.ai.teleprompter.align

/**
 * 单条匹配候选结果。
 *
 * @property tokenIndex 候选锚点指向的稿件 token 下标
 * @property confidence 0~1，1=字符完全相等，<1=模糊匹配
 * @property matchedText 实际匹配的文本（用于调试）
 */
data class AlignMatch(
    val tokenIndex: Int,
    val confidence: Float,
    val matchedText: String,
)

/**
 * 流式稿件匹配器 —— 把识别引擎返回的 partial/final hypothesis
 * 映射到稿件 token 序列的当前位置。
 *
 * 设计要点（参考 sherpa-onnx evb0110 / JulianGN 的做法）：
 *
 * 1. 稿件先做归一化（去标点 / 去空白 / 中文按字切分）成 token 序列 [w0, w1, ..., wn]
 * 2. ASR 每次返回一串文本片段（在滚动窗口里），同样归一化
 * 3. 在 [anchor-window..anchor+lookahead] 内做局部序列对齐
 * 4. 单调前进，最多接受 N 个 token 的跳跃
 * 5. 置信度 < 阈值不前进
 * 6. 双假设迟滞：两次 hypothesis 都指向同一新位置才推进
 *
 * 关键不变量：
 * - 不会回退（cursor 单调不减）
 * - 在没识别到任何东西时保持原位
 * - 大段跳跃只在 confidence 高 + lookahead 内连续命中时才放行
 */
class ScriptAligner(
    /** 原始稿件文本（中文直播稿，不需要分段） */
    scriptText: String,
    /** 一次最多前进的 token 数（默认 8：防 ASR 突然塞一大段假阳性时乱跳） */
    val maxAdvancePerStep: Int = 8,
    /** 模糊匹配相似度阈值，低于此值不前进（0~1） */
    val minConfidence: Float = 0.55f,
    /** 命中的 lookahead 窗口大小（按 token 计） */
    val lookAhead: Int = 24,
) {
    /** 归一化后的稿件 token 序列 */
    val tokens: List<String>

    /** cursor 是"已经读过的最后一个 token 下标"，初始 -1 表示没开始 */
    private var cursor: Int = -1

    /** 上一次的候选新位置（用于迟滞判定） */
    private var pendingCandidate: Int = -1
    private var pendingCandidateCount: Int = 0

    /** 上一次 finalize 后的 cursor（用于 reset） */
    private var lastFinalCursor: Int = -1

    init {
        tokens = normalize(scriptText)
        require(tokens.isNotEmpty()) { "稿件为空，无法启动提词器" }
    }

    /**
     * 处理一次 ASR 局部识别结果（partial 或 final hypothesis）。
     *
     * @param asrText 识别引擎返回的文本片段（增量或完整）
     * @param isFinal 是否为 final hypothesis（final 更可信，cursor 可以推进；partial 仅更新候选）
     * @return 新的 cursor 下标（>= 之前的 cursor）
     */
    fun update(asrText: String, isFinal: Boolean): Int {
        if (asrText.isBlank()) return cursor

        val asrTokens = normalize(asrText)
        if (asrTokens.isEmpty()) return cursor

        // 在 lookahead 窗口内搜索
        val anchor = cursor + 1
        val winStart = (anchor).coerceAtLeast(0)
        val winEnd = (anchor + lookAhead).coerceAtMost(tokens.size)

        if (winStart >= winEnd) {
            // 已经接近稿尾，没法再前进了，忽略
            return cursor
        }

        val match = findBestMatch(asrTokens, winStart, winEnd)
            ?: return cursor

        // 期望命中的下标
        val target = match.tokenIndex + match.matchedText.length - 1

        // 跳跃距离限制
        val advance = (target - cursor).coerceAtLeast(0)
        if (advance > maxAdvancePerStep) {
            // 跳跃太大，可能是 ASR 假阳性 + 我们已经落后太多
            // 但还是接受一段，作为"追赶"
            val capped = cursor + maxAdvancePerStep
            if (isFinal && match.confidence >= minConfidence) {
                cursor = capped
                return cursor
            }
            return cursor
        }

        if (match.confidence < minConfidence) {
            // 置信度不够，等下一次 hypothesis
            return cursor
        }

        if (!isFinal) {
            // partial 不直接推进 cursor，但可以记录候选
            if (target == pendingCandidate) {
                pendingCandidateCount++
                // 连续 2 次 partial 都指向同位置，可提前推进
                if (pendingCandidateCount >= 2) {
                    cursor = target
                    pendingCandidate = -1
                    pendingCandidateCount = 0
                }
            } else {
                pendingCandidate = target
                pendingCandidateCount = 1
            }
            return cursor
        }

        // final：直接推进
        cursor = target
        pendingCandidate = -1
        pendingCandidateCount = 0
        if (isFinal) lastFinalCursor = cursor
        return cursor
    }

    /**
     * 当前"已读完"的 token 下标。-1 表示还没开始。
     */
    fun currentIndex(): Int = cursor

    /**
     * 当前 token 之后的内容（用于 UI 显示剩余部分）。
     */
    fun remainingText(): String =
        if (cursor < 0) tokens.joinToString("")
        else tokens.drop(cursor + 1).joinToString("")

    /**
     * 已读完内容（用于 UI 显示"已讲过的部分"）。
     */
    fun spokenText(): String =
        if (cursor < 0) ""
        else tokens.take(cursor + 1).joinToString("")

    /**
     * 把 cursor 重置回开稿状态。
     */
    fun reset() {
        cursor = -1
        pendingCandidate = -1
        pendingCandidateCount = 0
        lastFinalCursor = -1
    }

    /**
     * 在 [winStart, winEnd) 范围内寻找 asrTokens 序列的最佳锚点。
     * 算法：从稿件窗口里取每个可能的起点 k，把 asrTokens 截到长度 ≤ 窗口，
     *       然后用最长公共子串 / 编辑距离算相似度。
     *
     * 这里用简化的"前缀 token 重合度"做近似：对每个 k，
     * 计算 fromTokens[k..k+len-1] 和 asrTokens[0..len-1] 的"重合度"。
     * len 由窗口剩余长度决定，取 ≤ min(winEnd-k, asrTokens.size, max(1, asrTokens.size-2))
     * 最终取重合度最高的 k。
     */
    private fun findBestMatch(
        asrTokens: List<String>,
        winStart: Int,
        winEnd: Int,
    ): AlignMatch? {
        var bestScore = 0f
        var bestK = winStart
        var bestLen = 0

        // 限制 len 上限，避免把"识别到的长串"全拿来对齐稿件 1 个位置
        val maxLen = minOf(asrTokens.size, 6, winEnd - winStart)
        if (maxLen <= 0) return null

        for (len in 1..maxLen) {
            val asrTail = asrTokens.takeLast(len)  // 只用识别结果的"末尾"，因为 ASR 增量返回
            for (k in winStart..(winEnd - len)) {
                val scriptSlice = tokens.subList(k, k + len)
                val score = similarity(asrTail, scriptSlice)
                if (score > bestScore) {
                    bestScore = score
                    bestK = k
                    bestLen = len
                }
            }
        }

        if (bestScore <= 0f) return null

        return AlignMatch(
            tokenIndex = bestK,
            confidence = bestScore,
            matchedText = tokens.subList(bestK, bestK + bestLen).joinToString(""),
        )
    }

    /**
     * 两个 token 序列的相似度。
     *
     * 中文按字切分后，"逐字相等"是主信号，
     * "拼音相同"是次要信号（防 ASR 同音字错误）。
     *
     * 这里给一个简单实现：相等字符数 / 总长度，
     * 加拼音近似后处理（如果装 pypinyin/tiny-segmenter 的话）。
     * 默认只用字面相似度。
     */
    private fun similarity(a: List<String>, b: List<String>): Float {
        if (a.isEmpty() || b.isEmpty()) return 0f
        val n = minOf(a.size, b.size)
        var match = 0
        for (i in 0 until n) {
            if (a[i] == b[i]) match++
            else {
                // 同音近似：字符集合很小时按 pinyin 算
                val pinyinA = PinyinCache.get(a[i])
                val pinyinB = PinyinCache.get(b[i])
                if (pinyinA.isNotEmpty() && pinyinA == pinyinB) match++
            }
        }
        return match.toFloat() / maxOf(a.size, b.size)
    }

    companion object {
        // 标点符号集合（含中文、英文、数字、引号、括号等）
        private val PUNCTUATION = "，。！？、；：\"'《》（）【】…—·.,!?;:()[]{}-\"'\\/0123456789"

        /**
         * 归一化：去标点 / 去空白 / 中文按字切 / 英文按词切
         * 直播稿通常就是中文，所以按字切是最稳的方案。
         */
        fun normalize(text: String): List<String> {
            val sb = StringBuilder()
            for (ch in text) {
                when {
                    ch.isWhitespace() -> continue
                    ch in PUNCTUATION -> continue
                    else -> sb.append(ch)
                }
            }
            // 按字符切分（中文单字足够，英文自然也是单字）
            return sb.toString().map { it.toString() }
        }
    }
}

/**
 * 拼音缓存：用 Android 系统的 android.text.TextUtils 没有直接拼音接口，
 * 实际生产应该用 [TinyPinyin](https://github.com/promeG/TinyPinyin) 或 pypinyin 的 JNI 移植。
 *
 * 这里给一个空实现（永远返回空字符串），即"不启用拼音近似"。
 * 之后可以替换为 Android 自带的 HanziToPinyin 或第三方库。
 *
 * 默认的相似度计算仍能工作 —— 因为 ASR 中文识别率足够高，逐字匹配已能 cover 大部分场景。
 */
internal object PinyinCache {
    fun get(ch: String): String = ""
}