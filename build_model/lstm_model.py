"""
LSTM 情感分类模型训练脚本（字符级）。

功能概述：
- 从 `data.csv` 读取训练数据（sentence、label）
- 构建字符到索引的词典（word_dict.pk）和标签到索引的词典（label_dict.pk）
- 训练 Embedding + LSTM + Softmax 三分类模型（积极/中性/消极）
- 保存模型到 `model/corpus_model.h5`

说明：
- 该脚本使用“字符级”建模：把每条 sentence 当作字符序列进行编码。
- 训练得到的 `word_dict.pk` 会在在线预测阶段复用，务必与模型配套保存。
"""

from __future__ import annotations

import os
import pickle
from typing import Dict, List, Tuple

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split

# 兼容导入：优先使用 TensorFlow 自带 Keras；若环境仅安装了 keras 则回退。
try:
    from tensorflow.keras.layers import LSTM, Dense, Dropout, Embedding
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.preprocessing.sequence import pad_sequences
    from tensorflow.keras.utils import to_categorical
except Exception:  # pragma: no cover
    from keras.layers import LSTM, Dense, Dropout, Embedding
    from keras.models import Sequential
    from keras.preprocessing.sequence import pad_sequences
    from keras.utils import to_categorical


# ------------------------------
# 可配置参数（按需调整）
# ------------------------------
DEFAULT_INPUT_LEN = 180  # 序列长度（不足 padding，超出截断）
DEFAULT_OUTPUT_DIM = 20  # Embedding 向量维度
DEFAULT_LSTM_UNITS = 100
DEFAULT_BATCH_SIZE = 32
DEFAULT_EPOCHS = 2


def _resolve_path(filepath: str, base_dir: str | None) -> Tuple[str, str]:
    """
    统一处理路径：
    - base_dir 为空时，默认使用 filepath 所在目录
    - filepath 为相对路径时，拼到 base_dir 下
    返回 (base_dir, absolute_filepath)
    """
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(filepath)) or "."
    if not os.path.isabs(filepath):
        filepath = os.path.join(base_dir, filepath)
    return base_dir, filepath

def load_data(
    filepath: str,
    input_len: int = 20,
    base_dir: str | None = None,
) -> Tuple[np.ndarray, np.ndarray, Dict[int, str], int, int, Dict[int, str]]:
    """
    读取并编码训练数据。

    参数：
    - filepath: CSV 路径（需要包含列：sentence、label）
    - input_len: 序列长度（padding 到固定长度）
    - base_dir: 词典输出目录（word_dict.pk、label_dict.pk 会写到这里）

    返回：
    - x: shape=(N, input_len) 的整数序列
    - y: shape=(N, label_size) 的 one-hot 标签
    - output_dictionary: {label_index: label_name}
    - vocab_size: 词典大小
    - label_size: 标签类别数
    - inverse_word_dictionary: {word_index: char}
    """
    base_dir, filepath = _resolve_path(filepath, base_dir)

    # 1) 读取数据
    df = pd.read_csv(filepath)
    if "sentence" not in df.columns or "label" not in df.columns:
        raise ValueError("CSV 必须包含列：sentence、label")

    # 2) 标签集合：用于构建 label -> index 的映射
    labels = list(df["label"].unique())

    # 3) 字符集合：把所有 sentence 拼接后取 set，得到字符级词表
    vocabulary_strings = list(df["sentence"].unique())
    all_chars = set("".join(str(item) for item in vocabulary_strings))

    # 4) 构建字符词典（索引从 1 开始，0 作为 padding/unknown）
    word_dictionary: Dict[str, int] = {ch: i + 1 for i, ch in enumerate(all_chars)}
    inverse_word_dictionary: Dict[int, str] = {i + 1: ch for i, ch in enumerate(all_chars)}

    # 5) 构建标签字典（索引从 0 开始，方便 one-hot）
    label_dictionary: Dict[str, int] = {label: i for i, label in enumerate(labels)}
    output_dictionary: Dict[int, str] = {i: label for i, label in enumerate(labels)}

    # 6) 保存词典，供预测阶段复用（在线预测会用 word_dict.pk）
    word_dict_path = os.path.join(base_dir, "word_dict.pk")
    with open(word_dict_path, "wb") as f:
        pickle.dump(word_dictionary, f)
    label_dict_path = os.path.join(base_dir, "label_dict.pk")
    with open(label_dict_path, "wb") as f:
        pickle.dump(label_dictionary, f)

    vocab_size = len(word_dictionary)
    label_size = len(label_dictionary)

    # 7) 编码 sentence（字符级）：未知字符用 0（与 padding 一致）
    x: List[List[int]] = [
        [word_dictionary.get(ch, 0) for ch in str(sent)]
        for sent in df["sentence"]
    ]
    x = pad_sequences(sequences=x, maxlen=input_len, padding="post", value=0)

    # 8) 编码 label：转为 one-hot
    y_index: List[int] = [label_dictionary[label] for label in df["label"]]
    y = to_categorical(y_index, num_classes=label_size)

    return x, y, output_dictionary, vocab_size, label_size, inverse_word_dictionary


def create_lstm_model(
    *,
    n_units: int,
    input_len: int,
    output_dim: int,
    vocab_size: int,
    label_size: int,
) -> Sequential:
    """
    创建 LSTM 模型结构。

    输入：长度为 input_len 的整数序列（字符索引）
    输出：label_size 维 softmax 概率（对应情感类别）
    """
    model = Sequential(name="lstm_sentiment_classifier")

    # +1：因为词典索引从 1 开始；0 保留为 padding/unknown
    model.add(
        Embedding(
            input_dim=vocab_size + 1,
            output_dim=output_dim,
            input_length=input_len,
            mask_zero=True,
            name="embedding"
        )
    )
    model.add(LSTM(n_units, name="lstm"))
    model.add(Dropout(0.2, name="dropout"))
    model.add(Dense(label_size, activation="softmax", name="classifier"))

    model.compile(
        loss="categorical_crossentropy",
        optimizer="adam",
        metrics=["accuracy"],
    )
    return model

def train_and_save(
    *,
    filepath: str,
    model_save_path: str,
    input_len: int = DEFAULT_INPUT_LEN,
    output_dim: int = DEFAULT_OUTPUT_DIM,
    n_units: int = DEFAULT_LSTM_UNITS,
    batch_size: int = DEFAULT_BATCH_SIZE,
    epochs: int = DEFAULT_EPOCHS,
    base_dir: str | None = None,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    训练并保存模型，返回 (y_pred, y_true)。
    """
    # 1) 编码数据 + 保存词典
    x, y, _, vocab_size, label_size, _ = load_data(filepath, input_len=input_len, base_dir=base_dir)

    # 2) 划分训练/测试集
    train_x, test_x, train_y, test_y = train_test_split(
        x, y, test_size=0.1, random_state=42
    )

    # 3) 创建模型并训练
    model = create_lstm_model(
        n_units=n_units,
        input_len=input_len,
        output_dim=output_dim,
        vocab_size=vocab_size,
        label_size=label_size,
    )
    model.summary()
    model.fit(train_x, train_y, epochs=epochs, batch_size=batch_size, verbose=1)

    # 4) 保存模型（确保目录存在）
    base_dir = base_dir or os.path.dirname(os.path.abspath(filepath)) or "."
    full_save_path = (
        model_save_path
        if os.path.isabs(model_save_path)
        else os.path.join(base_dir, model_save_path)
    )
    os.makedirs(os.path.dirname(full_save_path), exist_ok=True)
    model.save(full_save_path)

    # 5) 简单评估：测试集准确率
    y_pred = np.argmax(model.predict(test_x, verbose=0), axis=1)
    y_true = np.argmax(test_y, axis=1)
    acc = accuracy_score(y_true, y_pred)
    print(f"LSTM 模型预测准确率: {acc:.4f}")

    return y_pred, y_true

if __name__ == '__main__':
    # 以脚本所在目录作为基准目录，确保相对路径稳定
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # 训练数据（标注语料）：必须包含 sentence、label 两列
    train_csv = os.path.join(base_dir, "data.csv")

    # 模型输出路径（相对 base_dir）
    save_path = os.path.join("model", "corpus_model.h5")

    # 开始训练并保存模型
    train_and_save(
        filepath=train_csv,
        model_save_path=save_path,
        input_len=DEFAULT_INPUT_LEN,
        output_dim=DEFAULT_OUTPUT_DIM,
        n_units=DEFAULT_LSTM_UNITS,
        batch_size=DEFAULT_BATCH_SIZE,
        epochs=DEFAULT_EPOCHS,
        base_dir=base_dir
    )