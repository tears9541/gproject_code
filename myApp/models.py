"""
舆情评论明细模型。

该表是系统的核心数据载体，既用于“评论列表展示”，也作为统计分析（part1~part5）的明细来源。
在线爬取完成后会写入基础字段；在线情感推理会回写 `lstm_result/lstm_score` 两个字段。
"""

from datetime import datetime

from django.db import models


class CommentInfo(models.Model):
    """微博评论明细（含用户侧画像字段与情感预测字段）。"""
    comment_text = models.TextField(verbose_name='评论内容', default='暂无评论')
    # 注意：该字段在项目中实际存储的是 weibo 返回的 user.location（地区/属地），历史命名为“用户ip”
    area = models.CharField(max_length=100, verbose_name='用户ip')
    # 性别字段历史上可能出现：m / f / 男 / 女 / 未知
    # - 新爬取逻辑会尽量标准化为 “男/女/未知”
    gender = models.CharField(max_length=20, verbose_name='性别')
    fans_num = models.IntegerField(verbose_name='粉丝数')
    follow_num = models.IntegerField(verbose_name='关注数')
    pub_num = models.IntegerField(verbose_name='用户发布微博数')
    comment_date = models.DateTimeField(default=datetime.now, verbose_name='评论时间')
    keyword = models.CharField(max_length=100, verbose_name='评论所属热搜')
    lstm_result = models.CharField(max_length=100, verbose_name='情感倾向', default='未知情感')
    # 以字符串形式保存概率，便于兼容不同来源；使用时可转 float（模板/统计）
    lstm_score = models.CharField(max_length=50, verbose_name='情感得分', default='0.0')

    class Meta:
        verbose_name_plural = '评论管理'