import pandas as pd

df = pd.read_csv('data.csv')
label_map = {0: '消极', 1: '积极',2: '中性'}
df['label'] = df['label'].map(label_map)

df.to_csv('data.csv')