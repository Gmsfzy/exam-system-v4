from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user
from database.models import Exam, ExamSession, ExamStudent, Question, ExamQuestion, Answer, ExamStatusEnum, Result
from database import db
from datetime import datetime
import json

execution_bp = Blueprint('execution', __name__)

@execution_bp.route("/student/dashboard")
@login_required
def student_dashboard():
    if not current_user.is_student():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    now = datetime.now()

    # 获取学生已提交的考试（从 Result 表获取，这是最可靠的来源）
    student_results = Result.query.filter_by(student_id=current_user.id).all()
    # 构建 exam_id → Result 映射，供模板直接使用
    result_map = {r.exam_id: r for r in student_results}
    ended_exams = [r.exam for r in student_results if r.exam]

    submitted_exam_ids = set(result_map.keys())
    # 获取学生被邀请的考试
    invited_exams = Exam.query.join(ExamStudent).filter(ExamStudent.student_id == current_user.id).all()

    # 获取学生已参加的考试会话
    sessions = ExamSession.query.filter_by(student_id=current_user.id).all()
    session_exam_ids = [s.exam_id for s in sessions]

    # 活跃考试：被邀请的、未结束的、未提交的
    active_exams = []
    for exam in invited_exams:
        if exam.id in submitted_exam_ids:
            continue  # 已提交的不再显示为活跃
        is_ended = (exam.status == ExamStatusEnum.ENDED) or (exam.end_time and now > exam.end_time)
        if is_ended and exam.id not in submitted_exam_ids:
            # 已结束但未提交（超时自动结束），也放入已结束列表
            ended_exams.append(exam)
        else:
            active_exams.append(exam)

    return render_template('execution/dashboard.html',
                           active_exams=active_exams,
                           ended_exams=ended_exams,
                           result_map=result_map,
                           session_exam_ids=session_exam_ids)

@execution_bp.route("/exam/<int:exam_id>/start")
@login_required
def start_exam(exam_id):
    if not current_user.is_student():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(exam_id)

    # 检查考试状态
    if exam.status == ExamStatusEnum.DRAFT:
        flash('考试尚未发布', 'danger')
        return redirect(url_for('execution.student_dashboard'))
    if exam.status == ExamStatusEnum.ENDED:
        flash('考试已结束', 'danger')
        return redirect(url_for('execution.student_dashboard'))

    # 检查时间（使用本地时间，与 exam.start_time 保持一致）
    now = datetime.now()
    if now < exam.start_time:
        flash('考试尚未开始', 'danger')
        return redirect(url_for('execution.student_dashboard'))
    if now > exam.end_time:
        flash('考试已结束', 'danger')
        return redirect(url_for('execution.student_dashboard'))

    # 检查是否已被邀请
    invited = ExamStudent.query.filter_by(exam_id=exam_id, student_id=current_user.id).first()
    if not invited:
        flash('您未被邀请参加此考试', 'danger')
        return redirect(url_for('execution.student_dashboard'))

    # 创建或获取会话
    existing_session = ExamSession.query.filter_by(exam_id=exam_id, student_id=current_user.id, status='in_progress').first()

    if existing_session:
        session['current_session_id'] = existing_session.id
        return redirect(url_for('execution.take_exam', exam_id=exam_id))

    new_session = ExamSession(
        exam_id=exam_id,
        student_id=current_user.id,
        start_time=datetime.now(),
        status='in_progress'
    )
    db.session.add(new_session)
    db.session.commit()

    session['current_session_id'] = new_session.id
    return redirect(url_for('execution.take_exam', exam_id=exam_id))

@execution_bp.route("/exam/<int:exam_id>/take", methods=['GET', 'POST'])
@login_required
def take_exam(exam_id):
    if not current_user.is_student():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(exam_id)
    session_id = session.get('current_session_id')

    if not session_id:
        flash('请先开始考试', 'danger')
        return redirect(url_for('execution.student_dashboard'))

    exam_session = db.session.get(ExamSession, session_id)

    if request.method == 'POST':
        # 保存答案
        for key, value in request.form.items():
            if key.startswith('answer_'):
                question_id = int(key.replace('answer_', ''))

                existing_answer = Answer.query.filter_by(session_id=session_id, question_id=question_id).first()

                if existing_answer:
                    existing_answer.student_answer = value
                else:
                    answer = Answer(session_id=session_id, question_id=question_id, student_answer=value)
                    db.session.add(answer)

        db.session.commit()

        if 'submit' in request.form:
            # 提交考试
            return redirect(url_for('execution.submit_exam', exam_id=exam_id))

        flash('答案已保存', 'success')

    # 计算剩余时间（秒）
    elapsed = (datetime.now() - exam_session.start_time).total_seconds()
    remaining_seconds = max(0, exam.duration * 60 - elapsed)

    # 获取考试题目
    exam_questions = ExamQuestion.query.filter_by(exam_id=exam_id).order_by(ExamQuestion.order).all()
    questions = []

    for eq in exam_questions:
        question = db.session.get(Question, eq.question_id)
        options = []
        if question.options:
            try:
                options = json.loads(question.options)
            except:
                pass

        # 获取学生答案
        student_answer = None
        answer = Answer.query.filter_by(session_id=session_id, question_id=question.id).first()
        if answer:
            student_answer = answer.student_answer

        questions.append({
            'id': question.id,
            'content': question.content,
            'options': options,
            'type': question.type,
            'score': eq.score,
            'student_answer': student_answer
        })

    return render_template('execution/take_exam.html',
                           exam=exam,
                           questions=questions,
                           exam_session=exam_session,
                           remaining_seconds=int(remaining_seconds))


@execution_bp.route("/exam/<int:exam_id>/report_switch", methods=['POST'])
@login_required
def report_switch(exam_id):
    """切屏上报接口：前端检测到切屏时调用"""
    if not current_user.is_student():
        return jsonify({'error': '无权访问'}), 403

    session_id = session.get('current_session_id')
    if not session_id:
        return jsonify({'error': '无考试会话'}), 400

    exam_session = db.session.get(ExamSession, session_id)
    if not exam_session or exam_session.status != 'in_progress':
        return jsonify({'error': '考试已结束'}), 400

    exam_session.switch_count = (exam_session.switch_count or 0) + 1
    db.session.commit()

    return jsonify({
        'switch_count': exam_session.switch_count,
        'max_switches': 3,
        'auto_submitted': exam_session.switch_count >= 3
    })

@execution_bp.route("/exam/<int:exam_id>/submit")
@login_required
def submit_exam(exam_id):
    if not current_user.is_student():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    session_id = session.get('current_session_id')

    if not session_id:
        flash('请先开始考试', 'danger')
        return redirect(url_for('execution.student_dashboard'))

    exam_session = db.session.get(ExamSession, session_id)

    # 防止重复提交：若会话已提交，直接跳转成绩页
    if exam_session.status == 'submitted':
        existing_result = Result.query.filter_by(
            exam_id=exam_id, student_id=current_user.id
        ).first()
        if existing_result:
            return redirect(url_for('execution.view_result', result_id=existing_result.id))

    exam_session.end_time = datetime.now()
    exam_session.status = 'submitted'
    db.session.commit()

    # 调用AI批改（可能失败，包裹 try/except）
    earned_score = 0
    total_score = 0
    grading_failed = False
    try:
        from ai_service.services import ai_grade_exam
        earned_score, total_score = ai_grade_exam(db.session, exam_id, current_user.id)
    except Exception as e:
        grading_failed = True
        flash(f'AI批改暂时不可用（{str(e)[:50]}），成绩将待教师人工批改后公布', 'warning')

    # 无论AI是否成功，都创建成绩记录
    from database.models import Result
    result = Result(
        exam_id=exam_id,
        student_id=current_user.id,
        score=earned_score,
        total_score=total_score,
        submitted_at=datetime.now()
    )
    db.session.add(result)
    db.session.commit()

    # 清除考试会话
    session.pop('current_session_id', None)

    if not grading_failed:
        flash('考试提交成功！', 'success')

    return redirect(url_for('execution.view_result', result_id=result.id))

@execution_bp.route("/result/<int:result_id>")
@login_required
def view_result(result_id):
    if not current_user.is_student():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    result = Result.query.get_or_404(result_id)

    if result.student_id != current_user.id:
        flash('无权查看此成绩', 'danger')
        return redirect(url_for('execution.student_dashboard'))

    # 判断考试是否真正结束（状态为 ended 或 当前时间已超过截止时间）
    exam = Exam.query.get_or_404(result.exam_id)
    exam_ended = (exam.status == ExamStatusEnum.ENDED) or (exam.end_time and datetime.now() > exam.end_time)

    return render_template('execution/result.html', result=result, exam_ended=exam_ended)
