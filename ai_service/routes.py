from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from ai_service.services import ai_generate_questions
from database.models import Major, QuestionTypeEnum, DifficultyEnum
from database import db

ai_bp = Blueprint('ai', __name__)

# 创建中文映射字典（键使用小写，匹配 QuestionTypeEnum 实际值）
question_type_map = {
    'single_choice':   '单选题',
    'multiple_choice': '多选题',
    'fill_blank':      '填空题',
    'true_false':      '判断题',
    'short_answer':    '问答题',
    'programming':     '编程题',
    'application':     '应用题',
    'calculation':     '计算题',
}

difficulty_map = {
    'easy': '简单',
    'medium': '中等',
    'hard': '困难'
}

@ai_bp.route("/ai/generate", methods=['GET', 'POST'])
@login_required
def generate_questions():
    if not current_user.is_teacher():
        flash('无权访问', 'danger')
        return redirect(url_for('home'))

    if request.method == 'POST':
        major_name = request.form['major_name'].strip()  # 改为手动输入
        question_type = request.form['type']
        difficulty = request.form['difficulty']
        count = int(request.form.get('count', 5))

        if not major_name:
            flash('请输入专业名称', 'danger')
            return redirect(url_for('ai.generate_questions'))

        # 检查专业是否存在，不存在则创建
        major = Major.query.filter_by(name=major_name).first()
        if not major:
            major = Major(name=major_name)
            db.session.add(major)
            db.session.commit()
            db.session.refresh(major)

        try:
            questions = ai_generate_questions(db.session, major.id, question_type, difficulty, count)
            flash(f'Successfully generated {len(questions)} questions!', 'success')
        except Exception as e:
            flash(f'Failed to generate questions: {str(e)}', 'danger')

        return redirect(url_for('question_bank.list_questions'))

    majors = Major.query.all()
    # 获取中文显示的选项列表（value 使用实际枚举值，非属性名）
    question_types = [{'value': getattr(QuestionTypeEnum, t), 'label': question_type_map.get(getattr(QuestionTypeEnum, t), t)}
                      for t in dir(QuestionTypeEnum)
                      if not t.startswith('_') and isinstance(getattr(QuestionTypeEnum, t), str)]
    difficulties = [{'value': getattr(DifficultyEnum, d), 'label': difficulty_map.get(getattr(DifficultyEnum, d), d)}
                    for d in dir(DifficultyEnum)
                    if not d.startswith('_') and isinstance(getattr(DifficultyEnum, d), str)]

    return render_template('ai/generate.html', majors=majors,
                           question_types=question_types, difficulties=difficulties)
