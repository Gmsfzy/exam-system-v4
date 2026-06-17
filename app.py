from flask import Flask, render_template, redirect, url_for  # 添加 render_template
from flask_bcrypt import Bcrypt
from flask_login import LoginManager, current_user  # 添加 current_user
from config import Config
from database import db
from datetime import datetime

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)

bcrypt = Bcrypt(app)
login_manager = LoginManager(app)
login_manager.login_view = 'auth.login'
login_manager.login_message_category = 'info'

@login_manager.user_loader
def load_user(user_id):
    from database.models import User
    return db.session.get(User, int(user_id))

from auth.routes import auth_bp
from question_bank.routes import question_bp
from exam.routes import exam_bp
from exam_execution.routes import execution_bp
from result.routes import result_bp
from ai_service.routes import ai_bp

app.register_blueprint(auth_bp)
app.register_blueprint(question_bp)
app.register_blueprint(exam_bp)
app.register_blueprint(execution_bp)
app.register_blueprint(result_bp)
app.register_blueprint(ai_bp)


@app.before_request
def auto_end_expired_exams():
    """定时任务：自动结束已过截止时间的考试，并正确批改已作答的客观题"""
    from database.models import Exam, ExamSession, ExamStatusEnum, Answer, ExamQuestion, Result, Question, QuestionTypeEnum
    OBJECTIVE_TYPES = {'single_choice', 'multiple_choice', 'true_false', 'fill_blank'}
    try:
        now = datetime.now()
        expired_exams = Exam.query.filter(
            Exam.status == ExamStatusEnum.PUBLISHED,
            Exam.end_time < now
        ).all()
        for exam in expired_exams:
            exam.status = ExamStatusEnum.ENDED
            in_progress_sessions = ExamSession.query.filter_by(
                exam_id=exam.id, status='in_progress'
            ).all()
            for sess in in_progress_sessions:
                sess.end_time = now
                sess.status = 'submitted'
                # 创建成绩记录（若不存在）
                existing_result = Result.query.filter_by(
                    exam_id=exam.id, student_id=sess.student_id
                ).first()
                if not existing_result:
                    answers = Answer.query.filter_by(session_id=sess.id).all()
                    earned = 0
                    total = 0
                    for a in answers:
                        eq = ExamQuestion.query.filter_by(
                            exam_id=exam.id, question_id=a.question_id
                        ).first()
                        if not eq:
                            continue
                        total += eq.score
                        question = db.session.get(Question, a.question_id)
                        if not question:
                            continue
                        # 若 is_correct/score 尚未设置，则本地比对客观题
                        if a.is_correct is None:
                            student_ans = (a.student_answer or '').strip()
                            correct_ans = (question.answer or '').strip()
                            if question.type in OBJECTIVE_TYPES:
                                if question.type == 'multiple_choice':
                                    is_correct = ''.join(sorted(student_ans.upper())) == ''.join(sorted(correct_ans.upper()))
                                elif question.type == 'fill_blank':
                                    is_correct = student_ans.lower() == correct_ans.lower()
                                else:
                                    is_correct = student_ans.upper() == correct_ans.upper()
                            else:
                                is_correct = False
                                a.needs_manual_grade = True
                            a.is_correct = is_correct
                            a.score = eq.score if is_correct else 0
                        earned += (a.score or 0)
                    result = Result(
                        exam_id=exam.id,
                        student_id=sess.student_id,
                        score=earned,
                        total_score=total,
                        submitted_at=now
                    )
                    db.session.add(result)
        if expired_exams:
            db.session.commit()
    except Exception:
        db.session.rollback()

@app.route('/')
def home():
    # 如果已登录，根据角色重定向到对应的仪表盘
    if current_user.is_authenticated:
        if current_user.is_teacher():
            return redirect(url_for('exam.dashboard'))
        else:
            return redirect(url_for('execution.student_dashboard'))
    # 如果未登录，显示登录页面
    return render_template('home.html')

if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # 创建数据库表

        # 自动为现有表添加新字段（SQLite ALTER TABLE，已存在则忽略）
        new_columns = [
            ('answer', 'manual_score',     'FLOAT'),
            ('answer', 'manual_comment',   'TEXT'),
            ('answer', 'needs_manual_grade', 'BOOLEAN DEFAULT 0'),
            ('exam_session', 'switch_count', 'INTEGER DEFAULT 0'),
        ]
        for table, col, col_type in new_columns:
            try:
                db.session.execute(db.text(f'ALTER TABLE {table} ADD COLUMN {col} {col_type}'))
                db.session.commit()
                print(f'[DB] 已添加字段 {table}.{col}')
            except Exception:
                db.session.rollback()
                # 字段已存在，无需处理

        # 修正 AI 出题时存入的大写题型/难度值（SINGLE_CHOICE → single_choice）
        try:
            from database.models import Question
            fixed = 0
            for q in Question.query.all():
                changed = False
                if q.type and q.type != q.type.lower():
                    q.type = q.type.lower()
                    changed = True
                if q.difficulty and q.difficulty != q.difficulty.lower():
                    q.difficulty = q.difficulty.lower()
                    changed = True
                if changed:
                    fixed += 1
            if fixed > 0:
                db.session.commit()
                print(f'[DB] 已修正 {fixed} 道题目的题型/难度值为小写')
        except Exception:
            db.session.rollback()

    app.run(debug=True, use_reloader=False)
