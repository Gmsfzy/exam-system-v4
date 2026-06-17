from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from database.models import Exam, ExamQuestion, ExamStudent, User, Question, ExamStatusEnum, Major, QuestionTypeEnum
from database import db
from datetime import datetime
import random

exam_bp = Blueprint('exam', __name__)

@exam_bp.route("/dashboard")
@login_required
def dashboard():
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exams = Exam.query.filter_by(creator_id=current_user.id).all()
    return render_template('exam/dashboard.html', exams=exams)

@exam_bp.route("/exams/create", methods=['GET', 'POST'])
@login_required
def create_exam():
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        title = request.form['title']
        description = request.form.get('description', '')
        start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
        end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
        duration = int(request.form['duration'])

        if start_time >= end_time:
            flash('开始时间必须早于结束时间', 'danger')
            return redirect(url_for('exam.create_exam'))

        exam = Exam(
            title=title,
            description=description,
            start_time=start_time,
            end_time=end_time,
            duration=duration,
            creator_id=current_user.id,
            status=ExamStatusEnum.DRAFT
        )
        db.session.add(exam)
        db.session.commit()

        flash('考试创建成功', 'success')
        return redirect(url_for('exam.dashboard'))

    return render_template('exam/create.html')

@exam_bp.route("/exams/<int:id>/edit", methods=['GET', 'POST'])
@login_required
def edit_exam(id):
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(id)

    if exam.creator_id != current_user.id:
        flash('无权修改此考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    if request.method == 'POST':
        exam.title = request.form['title']
        exam.description = request.form.get('description', '')
        exam.start_time = datetime.strptime(request.form['start_time'], '%Y-%m-%dT%H:%M')
        exam.end_time = datetime.strptime(request.form['end_time'], '%Y-%m-%dT%H:%M')
        exam.duration = int(request.form['duration'])

        if exam.start_time >= exam.end_time:
            flash('开始时间必须早于结束时间', 'danger')
            return redirect(url_for('exam.edit_exam', id=id))

        db.session.commit()
        flash('考试更新成功', 'success')
        return redirect(url_for('exam.dashboard'))

    return render_template('exam/edit.html', exam=exam)

@exam_bp.route("/exams/<int:id>/publish")
@login_required
def publish_exam(id):
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(id)

    if exam.creator_id != current_user.id:
        flash('无权发布此考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    if exam.status != ExamStatusEnum.DRAFT:
        flash('只能发布草稿状态的考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    if not exam.exam_questions:
        flash('考试必须至少包含一道题目', 'danger')
        return redirect(url_for('exam.add_questions', id=id))

    exam.status = ExamStatusEnum.PUBLISHED
    db.session.commit()
    flash('考试发布成功', 'success')
    return redirect(url_for('exam.dashboard'))

@exam_bp.route("/exams/<int:id>/end")
@login_required
def end_exam(id):
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(id)

    if exam.creator_id != current_user.id:
        flash('无权结束此考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    if exam.status != ExamStatusEnum.PUBLISHED:
        flash('只能结束已发布的考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    exam.status = ExamStatusEnum.ENDED
    db.session.commit()
    flash('考试已结束', 'success')
    return redirect(url_for('exam.dashboard'))

@exam_bp.route("/exams/<int:id>/add_questions", methods=['GET', 'POST'])
@login_required
def add_questions(id):
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(id)

    if exam.creator_id != current_user.id:
        flash('无权修改此考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    if request.method == 'POST':
        question_ids = request.form.getlist('question_ids')
        for q_id in question_ids:
            existing = ExamQuestion.query.filter_by(exam_id=id, question_id=q_id).first()
            if not existing:
                max_order = ExamQuestion.query.filter_by(exam_id=id).count()
                eq = ExamQuestion(exam_id=id, question_id=q_id, order=max_order+1)
                db.session.add(eq)

        db.session.commit()
        flash('题目添加成功', 'success')
        return redirect(url_for('exam.add_questions', id=id))

    # 筛选参数
    filter_major_id = request.args.get('major_id', type=int)
    filter_type = request.args.get('type', '')

    # 获取未添加到该考试的题目
    added_ids = [eq.question_id for eq in exam.exam_questions]
    query = Question.query.filter(Question.id.notin_(added_ids))
    if filter_major_id:
        query = query.filter_by(major_id=filter_major_id)
    if filter_type:
        query = query.filter_by(type=filter_type)
    questions = query.all()

    # 筛选选项
    majors = Major.query.all()
    type_labels = {
        'single_choice': '单选题', 'multiple_choice': '多选题',
        'fill_blank': '填空题', 'true_false': '判断题',
        'short_answer': '问答题', 'programming': '编程题',
        'application': '应用题', 'calculation': '计算题',
    }

    return render_template('exam/add_questions.html',
                           exam=exam,
                           questions=questions,
                           majors=majors,
                           type_labels=type_labels,
                           filter_major_id=filter_major_id,
                           filter_type=filter_type)


@exam_bp.route("/exams/<int:id>/remove_question/<int:question_id>", methods=['POST'])
@login_required
def remove_question(id, question_id):
    """从考试中移除某道题目"""
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(id)
    if exam.creator_id != current_user.id:
        flash('无权修改此考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    eq = ExamQuestion.query.filter_by(exam_id=id, question_id=question_id).first()
    if eq:
        db.session.delete(eq)
        # 重新排序
        remaining = ExamQuestion.query.filter_by(exam_id=id).order_by(ExamQuestion.order).all()
        for i, r in enumerate(remaining, 1):
            r.order = i
        db.session.commit()
        flash('题目已移除', 'success')
    else:
        flash('题目不存在于该考试中', 'warning')

    return redirect(url_for('exam.add_questions', id=id))


@exam_bp.route("/exams/<int:id>/shuffle_questions", methods=['POST'])
@login_required
def shuffle_questions(id):
    """随机打乱考试中题目的顺序"""
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(id)
    if exam.creator_id != current_user.id:
        flash('无权修改此考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    exam_questions = ExamQuestion.query.filter_by(exam_id=id).all()
    if len(exam_questions) < 2:
        flash('题目数量不足，无法打乱', 'warning')
        return redirect(url_for('exam.add_questions', id=id))

    orders = [eq.order for eq in exam_questions]
    random.shuffle(orders)
    for eq, new_order in zip(exam_questions, orders):
        eq.order = new_order
    db.session.commit()

    flash('题目顺序已随机打乱', 'success')
    return redirect(url_for('exam.add_questions', id=id))

@exam_bp.route("/exams/<int:id>/invite", methods=['GET', 'POST'])
@login_required
def invite_students(id):
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(id)

    if exam.creator_id != current_user.id:
        flash('无权邀请学生', 'danger')
        return redirect(url_for('exam.dashboard'))

    if request.method == 'POST':
        student_ids = request.form.getlist('student_ids')
        for s_id in student_ids:
            existing = ExamStudent.query.filter_by(exam_id=id, student_id=s_id).first()
            if not existing:
                es = ExamStudent(exam_id=id, student_id=s_id)
                db.session.add(es)

        db.session.commit()
        flash('邀请成功', 'success')
        return redirect(url_for('exam.invite_students', id=id))

    # 获取未被邀请的学生
    invited_ids = [es.student_id for es in exam.exam_students]
    students = User.query.filter_by(role='student').filter(User.id.notin_(invited_ids)).all()

    return render_template('exam/invite.html', exam=exam, students=students)


@exam_bp.route("/exams/<int:id>/remove_student/<int:student_id>", methods=['POST'])
@login_required
def remove_student(id, student_id):
    """从考试邀请中移除某位学生"""
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(id)
    if exam.creator_id != current_user.id:
        flash('无权修改此考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    es = ExamStudent.query.filter_by(exam_id=id, student_id=student_id).first()
    if es:
        db.session.delete(es)
        db.session.commit()
        student = db.session.get(User, student_id)
        flash(f'已取消邀请「{student.username}」', 'success')
    else:
        flash('该学生未被邀请', 'warning')

    return redirect(url_for('exam.invite_students', id=id))

@exam_bp.route("/exams/<int:id>/results")
@login_required
def view_results(id):
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(id)

    if exam.creator_id != current_user.id:
        flash('无权查看此考试成绩', 'danger')
        return redirect(url_for('exam.dashboard'))

    return render_template('exam/results.html', exam=exam)
