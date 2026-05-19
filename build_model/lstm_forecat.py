import os
import pickle
import numpy as np
import pandas as pd
from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.sequence import pad_sequences


def load_test(df, max_length, base_dir=None):
    base_dir = base_dir or os.getcwd()
    word_dict_path = os.path.join(base_dir, 'word_dict.pk')
    with open(word_dict_path, 'rb') as f:
        word_dictionary = pickle.load(f)
    inverse_word_dictionary = {i: word for word, i in word_dictionary.items()}

    col = '评论内容' if '评论内容' in df.columns else df.columns[0]
    x = [[word_dictionary.get(word, 0) for word in str(sentence)] for sentence in df[col]]
    x = pad_sequences(sequences=x, maxlen=max_length, padding='post', value=0)

    return x, inverse_word_dictionary

def get_sentiment_label(predictions):
    neg, neu, pos = predictions[0]

    if neg > max(neu, pos) + 0.2:
        return '消极', neg
    elif pos > max(neu, neg) + 0.1:
        return '积极', pos
    else:
        return '中性', neu

def do_LSTM(input_shape=180, data_csv=None, base_dir=None):
    base_dir = base_dir or os.path.dirname(os.path.abspath(__file__))
    model_save_path = os.path.join(base_dir, 'model', 'corpus_model.h5')
    lstm_model = load_model(model_save_path)
    data_path = data_csv or os.path.join(os.path.dirname(base_dir), 'data', 'clean.csv')
    df = pd.read_csv(data_path)

    df['lstm_result'] = ''
    df['lstm_score'] = 0.0
    test_x, inverse_word_dictionary = load_test(df, input_shape, base_dir=base_dir)

    predictions = lstm_model.predict(test_x, verbose=0)
    for idx in range(len(df)):
        label, score = get_sentiment_label(predictions[idx:idx+1])
        confidence = np.max(predictions[idx])
        df.loc[idx, 'lstm_result'] = label
        df.loc[idx, 'lstm_score'] = round(score, 2)

        sentence = [inverse_word_dictionary.get(i, '') for i in test_x[idx] if i!=0]
        print(f"评论:{''.join(sentence)}")
        print(f"预测结果: {label}, 情感得分: {score: .2f}")
        print("-"*50)

    result_path = os.path.join(base_dir, 'LSTM_result.csv')
    df.to_csv(result_path, index=False)


if __name__ == '__main__':
    input_shape = 180
    do_LSTM(input_shape=input_shape)