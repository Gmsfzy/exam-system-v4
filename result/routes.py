from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from database.models import Result, Exam, Answer, Question, ExamSession, ExamQuestion, ExamStudent, User, ExamStatusEnum, QuestionTypeEnum
from ai_service.services import ai_generate_analysis
from database import db
from datetime import datetime
import json

result_bp = Blueprint('result', __name__)

@result_bp.route("/results/me")
@login_required
def my_results():
    if not current_user.is_student():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    results = Result.query.filter_by(student_id=current_user.id).all()
    return render_template('result/my_results.html', results=results, now=datetime.now(), ExamStatusEnum=ExamStatusEnum)

@result_bp.route("/results/exam/<int:exam_id>")
@login_required
def exam_results(exam_id):
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(exam_id)

    if exam.creator_id != current_user.id:
        flash('无权查看此考试成绩', 'danger')
        return redirect(url_for('exam.dashboard'))

    return render_template('result/exam_results.html', exam=exam)

@result_bp.route("/results/<int:result_id>")
@login_required
def view_result(result_id):
    result = Result.query.get_or_404(result_id)

    # 检查权限
    if current_user.is_student() and result.student_id != current_user.id:
        flash('无权查看此成绩', 'danger')
        return redirect(url_for('home'))

    if current_user.is_teacher():
        exam = db.session.get(Exam, result.exam_id)
        if exam.creator_id != current_user.id:
            flash('无权查看此成绩', 'danger')
            return redirect(url_for('home'))

    return render_template('result/detail.html', result=result)

@result_bp.route("/results/analysis/<int:exam_id>")
@login_required
def view_analysis(exam_id):
    student_id = request.args.get('student_id', type=int)

    if current_user.is_student():
        student_id = current_user.id
    elif not student_id:
        flash('请指定学生', 'danger')
        return redirect(url_for('exam.view_results', id=exam_id))

    # 检查考试是否已结束（状态为 ended 或 当前时间已超过截止时间）
    exam = Exam.query.get_or_404(exam_id)
    exam_ended = (exam.status == ExamStatusEnum.ENDED) or (exam.end_time and datetime.now() > exam.end_time)
    if not exam_ended:
        flash('考试尚未结束，无法查看解析', 'warning')
        if current_user.is_student():
            r = Result.query.filter_by(exam_id=exam_id, student_id=current_user.id).first()
            return redirect(url_for('execution.view_result', result_id=r.id) if r else url_for('execution.student_dashboard'))
        return redirect(url_for('home'))

    # 检查权限
    if current_user.is_student():
        if student_id != current_user.id:
            flash('无权查看他人解析', 'danger')
            return redirect(url_for('home'))
    else:
        if exam.creator_id != current_user.id:
            flash('无权查看此考试解析', 'danger')
            return redirect(url_for('home'))

    # 获取学生的答题记录
    session = ExamSession.query.filter_by(exam_id=exam_id, student_id=student_id).first()

    if not session:
        flash('未找到考试记录', 'danger')
        return redirect(url_for('home'))

    answers = Answer.query.filter_by(session_id=session.id).all()
    analysis_list = []

    OBJECTIVE_TYPES = {'single_choice', 'multiple_choice', 'true_false', 'fill_blank'}

    for answer in answers:
        question = db.session.get(Question, answer.question_id)
        if not question:
            continue

        # 获取解析
        analysis = question.analysis if question.analysis else ai_generate_analysis(None, question.id, answer.student_answer)

        options = []
        if question.options:
            try:
                options = json.loads(question.options)
            except:
                pass

        # 获取该题分值
        eq = ExamQuestion.query.filter_by(exam_id=exam_id, question_id=question.id).first()
        max_score = eq.score if eq else 0

        # 判断对错：若 is_correct 为 None 则本地比对
        is_correct = answer.is_correct
        score = answer.score
        if is_correct is None:
            student_ans = (answer.student_answer or '').strip()
            correct_ans = (question.answer or '').strip()
            if question.type in OBJECTIVE_TYPES:
                if question.type == 'multiple_choice':
                    is_correct = ''.join(sorted(student_ans.upper())) == ''.join(sorted(correct_ans.upper()))
                elif question.type == 'fill_blank':
                    is_correct = student_ans.lower() == correct_ans.lower()
                else:
                    is_correct = student_ans.upper() == correct_ans.upper()
            else:
                # 主观题：有分数则视为正确（AI 可能已评分），否则 None
                is_correct = (score is not None and score > 0) if score is not None else False
            # 计算分数
            if score is None:
                score = max_score if is_correct else 0

        analysis_list.append({
            'question_id': question.id,
            'content': question.content,
            'options': options,
            'student_answer': answer.student_answer,
            'correct_answer': question.answer,
            'is_correct': is_correct,
            'score': score,
            'max_score': max_score,
            'analysis': analysis
        })

    return render_template('result/analysis.html', exam=exam, analysis_list=analysis_list)


# ──────────────────────────────────────────────────────────
#  教师人工评分功能
# ──────────────────────────────────────────────────────────

@result_bp.route("/results/grading/<int:exam_id>")
@login_required
def grading_list(exam_id):
    """教师查看考试所有学生的评分状态列表"""
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(exam_id)
    if exam.creator_id != current_user.id:
        flash('无权访问此考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    # 获取所有成绩记录，附带人工评分状态
    results = Result.query.filter_by(exam_id=exam_id).all()
    students_info = []
    for r in results:
        session = ExamSession.query.filter_by(
            exam_id=exam_id, student_id=r.student_id
        ).first()
        if not session:
            continue
        # 统计主观题数量和已人工评分数量
        subjective_answers = (
            Answer.query.join(Question, Answer.question_id == Question.id)
            .filter(
                Answer.session_id == session.id,
                Question.type.in_(QuestionTypeEnum.SUBJECTIVE_TYPES)
            ).all()
        )
        total_subjective = len(subjective_answers)
        graded_count = sum(1 for a in subjective_answers if a.is_manual_graded)
        pending_count = total_subjective - graded_count

        students_info.append({
            'result': r,
            'student': r.student,
            'total_subjective': total_subjective,
            'graded_count': graded_count,
            'pending_count': pending_count,
        })

    return render_template('result/grading_list.html',
                           exam=exam, students_info=students_info)


@result_bp.route("/results/grading/<int:exam_id>/<int:student_id>",
                 methods=['GET', 'POST'])
@login_required
def grading_detail(exam_id, student_id):
    """教师对某学生的主观题进行人工评分"""
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    exam = Exam.query.get_or_404(exam_id)
    if exam.creator_id != current_user.id:
        flash('无权访问此考试', 'danger')
        return redirect(url_for('exam.dashboard'))

    session = ExamSession.query.filter_by(
        exam_id=exam_id, student_id=student_id
    ).first()
    if not session:
        flash('未找到考试记录', 'danger')
        return redirect(url_for('result.grading_list', exam_id=exam_id))

    student = User.query.get_or_404(student_id)

    if request.method == 'POST':
        # 保存人工评分
        for key, value in request.form.items():
            if key.startswith('manual_score_'):
                answer_id = int(key.replace('manual_score_', ''))
                answer = db.session.get(Answer, answer_id)
                if answer and answer.session_id == session.id:
                    try:
                        manual_score_val = float(value)
                    except (ValueError, TypeError):
                        continue

                    # 获取该题满分分值
                    eq = ExamQuestion.query.filter_by(
                        exam_id=exam_id, question_id=answer.question_id
                    ).first()
                    if not eq:
                        continue
                    # 限制分数范围 [0, 满分]
                    manual_score_val = max(0, min(manual_score_val, eq.score))
                    answer.manual_score = manual_score_val
                    answer.is_correct = (manual_score_val >= eq.score * 0.6)  # 60%以上视为正确

                    # 保存评语
                    comment_key = f'manual_comment_{answer_id}'
                    answer.manual_comment = request.form.get(comment_key, '').strip()
                    answer.needs_manual_grade = False

        # 重新计算总成绩（取 effective_score）
        all_answers = Answer.query.filter_by(session_id=session.id).all()
        new_earned = sum(a.effective_score for a in all_answers)

        # 更新 Result 表
        result = Result.query.filter_by(
            exam_id=exam_id, student_id=student_id
        ).first()
        if result:
            result.score = new_earned

        db.session.commit()
        flash(f'已保存「{student.username}」的人工评分', 'success')
        return redirect(url_for('result.grading_list', exam_id=exam_id))

    # GET：获取主观题答题列表
    subjective_items = []
    answers = Answer.query.filter_by(session_id=session.id).all()
    for answer in answers:
        question = db.session.get(Question, answer.question_id)
        if not question or not QuestionTypeEnum.is_subjective(question.type):
            continue
        eq = ExamQuestion.query.filter_by(
            exam_id=exam_id, question_id=question.id
        ).first()
        if not eq:
            continue
        options = []
        if question.options:
            try:
                options = json.loads(question.options)
            except:
                pass
        subjective_items.append({
            'answer': answer,
            'question': question,
            'exam_question': eq,
            'options': options,
            'type_label': QuestionTypeEnum.label(question.type),
        })

    return render_template('result/grading_detail.html',
                           exam=exam, student=student,
                           subjective_items=subjective_items)
