import os
from sqlalchemy import JSON
from flask import Flask, render_template, request, redirect, url_for, jsonify, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# ---------------- SECURITY CONFIG ----------------
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY')
if not app.config['SECRET_KEY']:
    raise RuntimeError("SECRET_KEY environment variable is not set")

app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///db.sqlite3'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SECURE'] = False  # Set to True in production with HTTPS
app.config['REMEMBER_COOKIE_HTTPONLY'] = True

db = SQLAlchemy(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)

DEFAULT_REACTIONS = {
    "like": 0,
    "love": 0,
    "laugh": 0
}

# ---------------- MODELS ----------------
class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(150), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.String(200), nullable=False)
    reactions = db.Column(JSON, nullable=False, default=lambda: DEFAULT_REACTIONS.copy())

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    user = db.relationship('User', backref='posts')


# ---------------- LOGIN ----------------
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ---------------- ROUTES ----------------
@app.route('/react/<int:post_id>', methods=['POST'])
@login_required
def react(post_id):
    data = request.get_json(silent=True)

    if not data or 'reaction' not in data:
        return jsonify({"success": False, "error": "Invalid request"}), 400

    reaction_type = data['reaction']
    post = db.session.get(Post, post_id)

    if not post:
        return jsonify({"success": False, "error": "Post not found"}), 404

    reactions = dict(post.reactions or DEFAULT_REACTIONS.copy())

    if reaction_type not in reactions:
        return jsonify({"success": False, "error": "Invalid reaction"}), 400

    reactions[reaction_type] += 1
    post.reactions = reactions
    db.session.commit()

    return jsonify({
        "success": True,
        "count": reactions[reaction_type]
    })


@app.route('/')
def home():
    if current_user.is_authenticated:
        return redirect(url_for('feed'))
    return redirect(url_for('login'))


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')

        if not username or not password:
            return render_template('register.html', error="All fields required")

        if len(password) < 8:
            return render_template('register.html', error="Password must be at least 8 characters")

        existing_user = User.query.filter_by(username=username).first()
        if existing_user:
            return render_template('register.html', error="Username already taken")

        user = User(username=username)
        user.set_password(password)

        db.session.add(user)
        db.session.commit()

        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username', '').strip().lower()
        password = request.form.get('password', '')
        remember = request.form.get('remember') == 'on'

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            login_user(user, remember=remember)
            return redirect(url_for('feed'))

        return render_template('login.html', error="Invalid credentials")

    return render_template('login.html')


@app.route('/feed', methods=['GET', 'POST'])
@login_required
def feed():
    if request.method == 'POST':
        content = request.form.get('content', '').strip()

        if not content:
            return redirect(url_for('feed'))

        if len(content) > 200:
            return render_template(
                'feed.html',
                posts=Post.query.order_by(Post.id.desc()).all(),
                user=current_user,
                error="Post must be 200 characters or fewer"
            )

        post = Post(content=content, user=current_user)
        db.session.add(post)
        db.session.commit()

        return redirect(url_for('feed'))

    posts = Post.query.order_by(Post.id.desc()).all()
    return render_template('feed.html', posts=posts, user=current_user)


@app.route('/logout', methods=['POST'])
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))


# ---------------- RUN ----------------
if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(debug=False)
