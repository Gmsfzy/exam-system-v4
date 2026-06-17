from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, current_user, logout_user, login_required
from database.models import User, RoleEnum
from database import db  # 修改：从 database 包导入 db

auth_bp = Blueprint('auth', __name__)

@auth_bp.route("/register", methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        email = request.form.get('email', '').strip() or None  # 空邮箱存 None，避免唯一约束冲突
        password = request.form['password']
        role = request.form['role']

        if User.query.filter_by(username=username).first():
            flash('用户名已存在', 'danger')
            return redirect(url_for('auth.register'))

        if email and User.query.filter_by(email=email).first():
            flash('邮箱已被注册', 'danger')
            return redirect(url_for('auth.register'))

        user = User(username=username, email=email, role=role)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        flash('您的账户已创建成功！请登录', 'success')
        return redirect(url_for('auth.login'))

    return render_template('register.html')

@auth_bp.route("/login", methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user)
            next_page = request.args.get('next')
            if user.is_teacher():
                return redirect(next_page or url_for('exam.dashboard'))
            else:
                return redirect(next_page or url_for('execution.student_dashboard'))
        else:
            flash('登录失败，请检查用户名和密码', 'danger')

    return render_template('login.html')

@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for('auth.login'))
