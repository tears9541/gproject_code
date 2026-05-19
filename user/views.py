"""
用户模块视图（登录/注册/个人中心/退出）。

设计说明：
- 登录与注册采用 AJAX + JSON 返回码方式，便于前端弹窗与跳转。
- 登录成功后将 `username/uid/avatar` 写入 session，用于全站头像与身份状态展示。
- 头像上传保存到 `static/img/` 下并更新 `UserInfo.avatar`。
"""

import os

from django.http import JsonResponse
from django.shortcuts import render, redirect

from user.models import UserInfo


def login(request):
    """登录：校验用户名密码，成功写 session 并返回 JSON。"""
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')

        try:
            user = UserInfo.objects.get(username=username)
        except UserInfo.DoesNotExist:
            # code=404：账号不存在
            return JsonResponse({'code':404, 'msg': '用户不存在'})
        if user.password == password:
            # 登录成功后写入 session，供后续页面读取
            request.session['username'] = username
            request.session['uid'] = user.id
            request.session['avatar'] = user.avatar
            return JsonResponse({'code': 200, 'msg': '登录成功'})
        else:
            # code=500：密码错误
            return JsonResponse({'code': 500, 'msg': '密码错误'})
    return render(request, 'login.html')


def register(request):
    """注册：对用户名/邮箱做唯一性校验，创建用户并返回 JSON。"""
    if request.method == 'POST':
        name = request.POST.get('name')
        email = request.POST.get('email')
        pwd = request.POST.get('pwd')

        if UserInfo.objects.filter(username=name).exists():
            # code=409：资源冲突（用户名已存在）
            return JsonResponse({'code':409, 'msg': '用户名已存在'})
        if UserInfo.objects.filter(uemail=email).exists():
            # code=409：资源冲突（邮箱已被注册）
            return JsonResponse({'code':409, 'msg': '该邮箱已被注册'})
        user = UserInfo(username=name, uemail=email, password=pwd)
        user.save()
        return JsonResponse({'code': 200, 'msg': '注册成功'})
    else:
        return render(request, 'register.html')

def userinfo(request):
    """个人中心：展示并允许修改个人资料/上传头像。"""
    uid = request.session.get('uid')
    avatar = request.session.get('avatar')
    user = UserInfo.objects.filter(id=uid).first()
    if request.method == 'POST':
        user.username = request.POST.get('username')
        user.password = request.POST.get('password')
        user.uemail = request.POST.get('uemail')
        user.uaddress = request.POST.get('uaddress')
        user.uyoubian = request.POST.get('uyoubian')
        user.uphone = request.POST.get('uphone')
        avatar = request.FILES.get('avatar')
        if avatar:
            # 头像保存到静态目录，便于模板直接引用
            static_images_dir = os.path.join(os.getcwd(), 'static', 'img')
            if not os.path.exists(static_images_dir):
                os.makedirs(static_images_dir)
            file_path = os.path.join(static_images_dir, avatar.name)
            with open(file_path, 'wb+') as destination:
                for chunk in avatar.chunks():
                    destination.write(chunk)
            user.avatar = os.path.join('/static/img', avatar.name)
        user.save()
        # 同步更新 session，避免刷新后仍显示旧头像
        request.session['avatar'] = user.avatar
        return redirect('user:userinfo')
    result = {
        'user_info': user,
        'avatar': avatar
    }
    return render(request, 'userinfo.html', result)

def logout(request):
    """退出登录：清空 session 并跳回登录页。"""
    request.session.clear()
    return redirect('user:login')