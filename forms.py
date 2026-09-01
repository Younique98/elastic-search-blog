"""Flask-WTF forms for the admin content-management UI.

Using FlaskForm gets CSRF protection, server-side validation, and
error-rendering for free/consistently across every admin form, instead of
hand-rolling each one the way the public-facing search forms in
templates/index.html do.
"""
from flask_wtf import FlaskForm
from wtforms import PasswordField, StringField, SubmitField, TextAreaField
from wtforms.validators import DataRequired, Length


class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Log in')


class PostForm(FlaskForm):
    name = StringField(
        'Title', validators=[DataRequired(), Length(max=200)]
    )
    summary = TextAreaField(
        'Summary',
        validators=[DataRequired(), Length(max=500)],
        description=(
            'A 1-2 sentence teaser shown in search results and used as '
            'this post’s meta description for search engines.'
        ),
    )
    content = TextAreaField('Content', validators=[DataRequired()])
    category = StringField('Category', validators=[DataRequired()])
    tags = StringField(
        'Tags',
        description='Comma-separated, e.g. "python, tutorials, elasticsearch"',
    )
    submit = SubmitField('Save post')
