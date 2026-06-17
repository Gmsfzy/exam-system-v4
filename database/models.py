from datetime import datetime
from flask_login import UserMixin
from database import db  # 从 database 包导入 db

class RoleEnum:
    TEACHER = "teacher"
    STUDENT = "student"

class ExamStatusEnum:
    DRAFT = "draft"
    PUBLISHED = "published"
    ENDED = "ended"

class QuestionTypeEnum:
    SINGLE_CHOICE = "single_choice"
    MULTIPLE_CHOICE = "multiple_choice"
    FILL_BLANK = "fill_blank"
    TRUE_FALSE = "true_false"
    SHORT_ANSWER = "short_answer"
    PROGRAMMING = "programming"       # 编程题
    APPLICATION = "application"       # 应用题
    CALCULATION = "calculation"       # 计算题

    # 主观题集合：这些题型支持教师人工评分
    SUBJECTIVE_TYPES = {SHORT_ANSWER, PROGRAMMING, APPLICATION, CALCULATION}

    @classmethod
    def is_subjective(cls, q_type: str) -> bool:
        """判断是否为需要人工评分的主观题"""
        return q_type in cls.SUBJECTIVE_TYPES

    @classmethod
    def label(cls, q_type: str) -> str:
        """返回题型的中文名称"""
        return _QUESTION_TYPE_LABELS.get(q_type, q_type)


_QUESTION_TYPE_LABELS = {
    'single_choice':   '单选题',
    'multiple_choice': '多选题',
    'fill_blank':      '填空题',
    'true_false':      '判断题',
    'short_answer':    '问答题',
    'programming':     '编程题',
    'application':     '应用题',
    'calculation':     '计算题',
}

class DifficultyEnum:
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(20), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True)  # , nullable=False)
    password_hash = db.Column(db.String(60), nullable=False)
    role = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def set_password(self, password):
        from app import bcrypt
        self.password_hash = bcrypt.generate_password_hash(password).decode('utf-8')

    def check_password(self, password):
        from app import bcrypt
        return bcrypt.check_password_hash(self.password_hash, password)

    def is_teacher(self):
        return self.role == RoleEnum.TEACHER

    def is_student(self):
        return self.role == RoleEnum.STUDENT

class Major(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)
    description = db.Column(db.Text)

    questions = db.relationship('Question', backref='major', lazy=True, cascade='all, delete-orphan')

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    options = db.Column(db.Text)  # JSON格式存储选项
    answer = db.Column(db.Text, nullable=False)
    analysis = db.Column(db.Text)
    major_id = db.Column(db.Integer, db.ForeignKey('major.id'), nullable=False)
    type = db.Column(db.String(20), nullable=False)
    difficulty = db.Column(db.String(20), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class Exam(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    start_time = db.Column(db.DateTime, nullable=False)
    end_time = db.Column(db.DateTime, nullable=False)
    duration = db.Column(db.Integer, nullable=False)  # 分钟
    status = db.Column(db.String(20), nullable=False, default=ExamStatusEnum.DRAFT)
    creator_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    creator = db.relationship('User', backref='exams', lazy=True)
    exam_questions = db.relationship('ExamQuestion', backref='exam', lazy=True)
    exam_students = db.relationship('ExamStudent', backref='exam', lazy=True)
    sessions = db.relationship('ExamSession', backref='exam', lazy=True)
    results = db.relationship('Result', backref='exam', lazy=True)

class ExamQuestion(db.Model):
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), primary_key=True)
    score = db.Column(db.Float, nullable=False, default=1.0)
    order = db.Column(db.Integer, nullable=False)

    question = db.relationship('Question')

class ExamStudent(db.Model):
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), primary_key=True)
    invited_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    student = db.relationship('User')

class ExamSession(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    status = db.Column(db.String(20), nullable=False, default='in_progress')
    switch_count = db.Column(db.Integer, default=0)  # 切屏次数

    student = db.relationship('User', backref='exam_sessions', lazy=True)
    answers = db.relationship('Answer', backref='session', lazy=True)

class Answer(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('exam_session.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id'), nullable=False)
    student_answer = db.Column(db.Text)
    is_correct = db.Column(db.Boolean)
    score = db.Column(db.Float)                  # AI 评分
    manual_score = db.Column(db.Float)           # 教师人工评分（None 表示未人工评分）
    manual_comment = db.Column(db.Text)          # 教师评语
    needs_manual_grade = db.Column(db.Boolean, default=False)  # 是否需要人工评分

    @property
    def effective_score(self):
        """有效得分：有人工评分时取人工，否则取 AI"""
        return self.manual_score if self.manual_score is not None else (self.score or 0)

    @property
    def is_manual_graded(self):
        """是否已人工评分"""
        return self.manual_score is not None

class Result(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    exam_id = db.Column(db.Integer, db.ForeignKey('exam.id'), nullable=False)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    score = db.Column(db.Float, nullable=False)
    total_score = db.Column(db.Float, nullable=False)
    submitted_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    ai_analysis = db.Column(db.Text)

    student = db.relationship('User', backref='results', lazy=True)
