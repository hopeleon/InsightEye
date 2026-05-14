# InsightEye 声纹识别技术文档

> 当前版本：v3+（Best-of-N × Mahalanobis × PLDA 三层打分 + 音频增强注册 版）
> 更新日期：2026-04-29
> v2 特性整合：音频数据增强 + 对角协方差精度向量 + PLDA 概率模型

---

## 1. 整体架构

```
音频输入 (16kHz float32)
    │
    ├── VAD (Silero VAD) — 语音活动检测，切分连续音频流
    │
    ├── 声纹变化检测 — 基于 embedding 聚类稳定性，检测同段内是否换人
    │
    ├── 声纹提取 — CAM++ 192维向量
    │
    └── 识别引擎
            ├── 注册质量评估 (RegistrationQualityAssessor)
            ├── 说话人注册表 (MultiSpeakerRegistry)
            │       └── 级联匹配引擎 (CascadeMatchingEngine)
            │               ├── Best-of-N Cosine 打分
            │               ├── Mahalanobis Distance（精度向量版）
            │               ├── PLDA Score（说话人假设对数似然比）
            │               └── 自适应 Boost（乘法修正）
            ├── 三层信号兜底纠正（Cosine / Mahalanobis / PLDA）
            ├── 多窗口投票融合 (match_with_voting)
            └── 动态阈值 (DynamicThresholdController)
```

---

## 2. 声纹模型

- **模型**：CAM++（CAM++_CN_common），中文说话人识别模型
- **向量维度**：192维
- **向量性质**：L2归一化后，单位球面上的方向向量
- **设备**：CUDA（GPU）

---

## 3. 声纹注册

### 3.1 注册流程

```
用户提供多段音频（建议 ≥2 段）
    │
    ├── 每段独立提取 192维 embedding
    │
    ├── RegistrationQualityAssessor 评估质量
    │       ├── 样本间一致性检测（cosine 相似度，阈值 0.75）
    │       ├── 离群样本检测（对角协方差马氏距离）
    │       ├── 样本方差控制（阈值 0.08）
    │       └── 重复注册检测（与已注册说话人的 cosine，阈值 0.85）
    │
    ├── 音频数据增强（AudioAugmentor，v2 移植）
    │       对每条原始音频生成多个增强版本：
    │       ├── 加噪（轻/中两档）— 模拟不同信噪比环境
    │       ├── 混响（单径延迟衰减）— 模拟不同房间
    │       ├── 变速（±5%）— 轻微语速变化
    │       └── 变调（±2%）— 轻微音高变化
    │       每个增强音频提取对应的 embedding，全部加入注册样本
    │
    ├── SpeakerModelTrainer 训练说话人统计模型（v2 移植）
    │       用全部 embedding（原始+增强）计算：
    │       ├── 均值向量 embedding_mean（归一化）
    │       ├── 逐维方差向量 embedding_var（对角协方差）
    │       └── 逐维精度向量 embedding_precision = 1/var（用于 Mahalanobis/PLDA）
    │
    └── 写入 SpeakerProfile + CascadeMatchingEngine + PLDA 全局统计
```

### 3.2 注册质量分（0~1）

| 条件 | 扣分倍率 |
|------|----------|
| 样本间均值相似度 < 0.75 | ×0.6（拒绝风险） |
| 样本间标准差 > 0.08 | ×0.7 |
| 检测到离群样本 | ×0.75 |
| 与已注册说话人相似度 > 0.85 | ×0.4（重复注册警告） |

### 3.3 存储的数据

每个说话人存储：
- **均值 embedding**：192维，声纹主向量（原始+增强样本的均值，归一化后）
- **individual_embeddings**：每段原始样本的192维向量列表（**用于识别时 Best-of-N 匹配**）
- **embedding_std**：192维逐维标准差（sqrt(var)，兼容旧字段）
- **embedding_precision**：192维逐维精度向量（**1/var，v2 新增，用于 Mahalanobis/PLDA**）
- 注册质量分、样本数量（含增强）、注册时间

---

## 4. 声纹识别（核心打分）

> **当前版本**：Best-of-N Cosine × Mahalanobis × PLDA，三项乘积融合 + Boost 乘法修正。

### 4.1 三层打分公式

对于 probe 音频的 embedding `p`，与已注册说话人 `s`：

```
1. Best-of-N Cosine（对每个原始注册 embedding 分别比，取最大值）：
    best_cosine = max( cosine(p, emb_1), ..., cosine(p, emb_N) )

2. Mahalanobis Distance（v2 重写为精度向量版，N≥3 激活）：
    mahal = sqrt( Σ_i (p_i - mean_i)² × precision_i )
           = sqrt( Σ_i (p_i - mean_i)² / var_i )
    mahal_score = clip( 1 / (1 + mahal × 0.1), 0, 1 )
    → 分布中心处 mahal=0 → mahal_score=1.0，越远越低
    → 相比旧版（直接用 std）：precision = 1/var 在数学上更正确

3. PLDA Score（v2 新增，说话人假设对数似然比）：
    mahal_same  = probe 到该说话人均值的马氏距离
    mahal_diff  = probe 到全局均值的马氏距离（pooled precision）
    LLR         = 0.5 × (mahal_same - mahal_diff)
    plda_score  = 1 / (1 + exp(-LLR))   ∈ (0, 1)
    → LLR > 0 → 同一人可能性更大（probe 更靠近该说话人分布）
    → LLR < 0 → 不同人可能性更大（probe 更靠近全局分布）

4. 自适应 Boost（仅基于历史 + 样本数量）：
    boost = 0.5
             + 历史加成(最多+0.3，同一说话人最近5次识别每出现一次+0.15)
             + min(0.1, N × 0.03)

5. 最终分数（三信号乘法 + Boost 修正）：
    product      = best_cosine × mahal_score × plda_score
    smooth       = cbrt(product)               （立方根平滑，保持 [0,1]）
    boost_factor = 0.8 + boost × 0.4           ∈ [0.8, 1.2]
    final        = smooth × boost_factor
```

### 4.2 权重与融合设计

| 层面 | 策略 | 说明 |
|------|------|------|
| Cosine × Mahal × PLDA | 乘法融合 | 任一信号低则乘积低，三信号互补，任一偏低都拉低总分，更严格 |
| Boost Factor | 乘法修正 [0.8, 1.2] | 仅做 ±20% 微调，不挤压 cosine 空间 |
| 立方根平滑 | cbrt(product) | product ∈ [0,1]，cbrt 拉伸低值区域，避免乘积崩塌 |
| PLDA 冷启动 | N≥2 时自动 fallback | 全局统计不足时用说话人自己的 precision 替代 pooled precision |

### 4.3 PLDA 全局统计更新

每当有说话人注册或注销时，更新全局 PLDA 统计：
- **global_mean**：所有已注册说话人均值向量的均值（归一化）
- **within_cov**：各说话人内方差的均值（对角向量）— 衡量同一人不同音频的差异
- **between_cov**：各说话人均值之间的方差（对角向量）— 衡量不同人之间的差异

---

## 5. 三层信号兜底纠正

在 `identify_with_voting` 的投票融合之后，加入第三层纠错机制：

```
对每个候选说话人，分别计算其在所有窗口上的：
    Layer 1: Best-of-N Cosine 均值
    Layer 2: Mahalanobis Score 均值
    Layer 3: PLDA Score 均值

每层取该层得分最高的说话人作为该层的 top1。

纠正规则：
    - 如果 VoteFusion 的 top1 在三层中完全没有支持（0/3 层认可）→ 强制纠正为多数层支持的说话人
    - 如果 VoteFusion 的 top1 只被 1/3 层支持，另两层一致同意另一个候选 → 纠正
    - 至少 2/3 层同意才执行纠正，避免单层噪声触发误纠正
```

**为什么三层比单层更可靠：**
- Cosine 擅长捕捉方向相似性，但对声纹稳定性的判别力弱
- Mahalanobis 捕捉 probe 是否落在说话人的分布范围内
- PLDA 捕捉 probe 是"该说话人"还是"只是一个普通人"（概率视角）
三层互相独立，错误模式不同，叠加后误判率大幅下降。

---

## 6. 说话人分离（VAD + 声纹变化检测）

### 6.1 两级分段机制

#### 第一级：静音超时（VAD）

- **触发条件**：连续 `min_silence_samples` 帧为静音（默认 1024ms）
- **作用**：自然停顿处切分，同一说话人的多次发言会分段

#### 第二级：声纹变化检测

- **触发条件**：同一次语音活动（静音分段之前）内部检测到换人
- **原理**：同一人 8~60 秒内的 embedding 自然聚成一个紧凑簇。换人时 embedding 跳到新位置，两两距离矩阵出现双簇结构
- **算法**：

```
条件1：最近3个 embedding 都显著偏离基准
    all(distance > threshold for distance in recent_3)

条件2：embedding 聚类分离度 > 1.5
    separation = max_pairwise_distance / mean_pairwise_distance
    （同一人 ≈1，换人 >1.5）

两层同时满足 → 触发声纹变化分段
```

### 6.2 保护机制

| 机制 | 参数 | 作用 |
|------|------|------|
| Warmup | 说话开始后 8 秒内不检测 | 等待声音稳定 |
| 最小检测样本 | 至少 N 个 embedding | 避免早期误判 |
| 最小段长 | 5 秒 | 避免短语音误分段 |
| 最小间隔 | 10 秒 | 避免连续误触发 |

---

## 7. 分段一致性验证

当一次识别有多个窗口 embedding 时（`identify_with_voting`），在三层纠正后进行一致性验证：

### 7.1 两层一致性

```
综合一致性 = 窗口对 top-1 Best-of-N 均值 × 窗口互一致性

窗口对 top-1 Best-of-N 均值：
    对每个窗口 embedding p_i，用 Best-of-N 与 top-1 的每个注册样本比
    取该窗口的最佳 cosine，最后对所有窗口取均值

窗口互一致性：
    所有窗口 embedding 两两之间的 cosine 均值
    → 同一人说话，各窗口 embedding 应该相似
    → 若某窗口与其他窗口都远 → 可能不是该说话人
```

### 7.2 uncertain 判定

`consistency < 0.55` 时直接标记 uncertain，同时结合以下条件：

| 条件 | 阈值 | 说明 |
|------|------|------|
| 置信度 | < 0.50 | 单次匹配置信度不足 |
| 分数绝对值 | < 动态阈值 | 低于动态阈值 |
| 与第二名差距 | < 0.05 | 第一名优势不明显 |
| 综合一致性 | < 0.55 | 多窗口不一致 |

---

## 8. 投票融合（多窗口）

当一次识别有多段 embedding 时，使用 `match_with_voting` 融合：

```
方法：score_weighted（分数加权）

对于每个候选说话人 s：
    score = Σ (embedding_i 的 top-k 中 s 的最终分数 × 排名权重) / Σ 排名权重
    其中排名权重 = 1 / (rank + 1)
    每个 embedding 只贡献一次（取最高排名的那次）
```

---

## 9. 关键参数汇总

| 参数 | 值 | 说明 |
|------|------|------|
| `BOOST_WEIGHT` | 已移除 | Boost 改为乘法因子（0.8~1.2），不再独立占权重 |
| `MIN_CONFIDENT_SCORE` | 0.65 | uncertain 判定阈值 |
| `CONSISTENCY_THRESHOLD` | 0.55 | 多窗口综合一致性阈值 |
| `CHANGE_DISTANCE_THRESHOLD` | 0.60 | 声纹变化距离阈值 |
| `DYNAMIC_FACTOR` | 2.5 | 动态阈值乘数 |
| `WARMUP_DURATION_MS` | 8000 | 声纹变化检测预热时间 |
| `MIN_CHANGE_INTERVAL_MS` | 10000 | 两次变化检测最小间隔 |
| `MIN_SAMPLES_FOR_REGISTRATION` | 2 | 最少注册样本数 |
| `AUGMENTED_SAMPLES_PER_AUDIO` | 3 | 每条音频最多生成增强样本数 |
| PLDA 冷启动阈值 | N≥2 说话人 | 全局统计生效所需最小说话人数 |

---

## 10. 版本历史

| 版本 | 核心打分 | 关键变化 |
|------|---------|---------|
| v1 | Cosine vs 均值 | 基础实现，L1 硬切线 |
| v2 | Cosine + Z-norm | 引入 ScoreNormalizer 归一化（未接入 pipeline，存于 enhanced_speaker_recognition_v2.py） |
| v3 | Best-of-N Cosine | probe 与每个注册样本分别比取最佳，移除均值偏移问题 |
| v3+（当前） | Best-of-N Cosine × Mahalanobis × PLDA | 整合 v2：精度向量马氏距离 + PLDA 概率模型 + 音频数据增强 + 三层兜底纠正 |

