from django.contrib import admin
from .models import CommentInfo

class CommentInfoAdmin(admin.ModelAdmin):
    list_display = ('comment_text', 'area', 'gender', 'fans_num', 'follow_num',
                    'pub_num', 'comment_date', 'keyword', 'lstm_result', 'lstm_score')
    search_fields = ('comment_text', 'area', 'gender', 'keyword')
    list_filter = ('gender', 'comment_date', 'keyword')

admin.site.register(CommentInfo, CommentInfoAdmin)