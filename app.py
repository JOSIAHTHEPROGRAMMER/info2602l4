import os
from flask import Flask, request, render_template, flash, redirect, url_for, jsonify
from functools import wraps
from models import db, Admin, RegularUser, Todo, User

from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    get_jwt_identity,
    jwt_required,
    current_user,
    set_access_cookies,
    unset_jwt_cookies,
    current_user,
)


def create_app():
  app = Flask(__name__, static_url_path='/static')
  app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
  app.config['TEMPLATES_AUTO_RELOAD'] = True
  app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(app.root_path, 'data.db')
  app.config['DEBUG'] = True
  app.config['SECRET_KEY'] = 'MySecretKey'
  app.config['PREFERRED_URL_SCHEME'] = 'https'
  app.config['JWT_ACCESS_COOKIE_NAME'] = 'access_token'
  app.config['JWT_REFRESH_COOKIE_NAME'] = 'refresh_token'
  app.config["JWT_TOKEN_LOCATION"] = ["cookies"]
  app.config["JWT_COOKIE_SECURE"] = True
  app.config["JWT_SECRET_KEY"] = "super-secret"
  app.config["JWT_COOKIE_CSRF_PROTECT"] = False
  app.config["JWT_ACCESS_TOKEN_EXPIRES"] = 60 * 60 * 24 * 7  # 1 week
  db.init_app(app)
  app.app_context().push()
  return app


app = create_app()
jwt = JWTManager(app)

#tells flask jwt how to pull a user object when the user_id id decoded from a token
@jwt.user_lookup_loader
def user_lookup_callback(_jwt_header, jwt_data):
  identity = jwt_data["sub"]
  return User.query.get(identity)

#Defines what page to show when token is invalid

@jwt.invalid_token_loader
def custom_unauthorized_response(error):
    return render_template('401.html', error=error), 401

#Defines what page to show when token is expired
@jwt.expired_token_loader
def expired_token_callback(jwt_header, jwt_payload):
    return render_template('401.html'), 401 

# custom decorator authorize routes for admin or regular user
def login_required(required_class):
  def wrapper(f):
    @wraps(f)
    @jwt_required()  # Ensure JWT authentication
    def decorated_function(*args, **kwargs):
      user = User.query.get(get_jwt_identity())
      if user.__class__ != required_class:  # Check class equality
        return jsonify(message='Invalid user role'), 403
      return f(*args, **kwargs)
    return decorated_function
  return wrapper

#tells flask jwt to encode the user's id in the token
def login_user(username, password):
  user = User.query.filter_by(username=username).first()
  if user and user.check_password(password):
    token = create_access_token(identity=user.id)
    return token
  return None

# View Routes


@app.route('/', methods=['GET'])
@app.route('/login', methods=['GET'])
def login_page():
  return render_template('login.html')


@app.route('/app', methods=['GET'])
@jwt_required()
def todos_page():
  return render_template('todo.html', current_user=current_user)


@app.route('/signup', methods=['GET'])
def signup_page():
  return render_template('signup.html')


@app.route('/editTodo/<id>', methods=["GET"])
@jwt_required()
def edit_todo_page(id):
  todos = Todo.query.all()
  todo = Todo.query.filter_by(id=id, user_id=current_user.id).first()

  if todo:
    return render_template('edit.html', todo=todo, current_user=current_user)

  flash('Todo not found or unauthorized')
  return redirect(url_for('todos_page'))


# Action Routes
@app.route('/signup', methods=['POST'])
def signup_action():
  data = request.form  # get data from form submission
  newuser = RegularUser(username=data['username'], email=data['email'], password=data['password'])  # create user object
  response = None
  try:
    db.session.add(newuser)
    db.session.commit()  # save user
    token = login_user(data['username'], data['password'])
    response = redirect(url_for('todos_page'))
    set_access_cookies(response, token)
    flash('Account Created!')  # send message
  except Exception:  # attempted to insert a duplicate user
    db.session.rollback()
    flash("username or email already exists")  # error message
    response = redirect(url_for('login_page'))
  return response


@app.route('/login', methods=['POST'])
def login_action():
  data = request.form
  token = login_user(data['username'], data['password'])
  print(token)
  response = None
  user = User.query.filter_by(username=data['username']).first()
  if token:
    flash('Logged in successfully.')  # send message to next page
    if user.type == "regular user":
      response = redirect(url_for('todos_page'))
    else :
      response = redirect(url_for('admin_page'))  # redirect to main page if login successful
    set_access_cookies(response, token)
  else:
    flash('Invalid username or password')  # send message to next page
    response = redirect(url_for('login_page'))
  return response

@app.route('/createTodo', methods=['POST'])
@jwt_required()
def create_todo_action():
  data = request.form
  current_user.add_todo(data['text'])
  flash('Created')
  return redirect(url_for('todos_page'))

@app.route('/toggle/<id>', methods=['POST'])
@jwt_required()
def toggle_todo_action(id):
  todo = current_user.toggle_todo(id)
  if todo is None:
    flash('Invalid id or unauthorized')
  else:
    flash(f'Todo { "done" if todo.done else "not done" }!')
  return redirect(url_for('todos_page'))

@app.route('/editTodo/<id>', methods=["POST"])
@jwt_required()
def edit_todo_action(id):
  data = request.form
  res = current_user.update_todo(id, data["text"])
  if res:
    flash('Todo Updated!')
  else:
    flash('Todo not found or unauthorized')
  return redirect(url_for('todos_page'))

@app.route('/deleteTodo/<id>', methods=["GET"])
@jwt_required()
def delete_todo_action(id):
  res = current_user.delete_todo(id)
  if res == None:
    flash('Invalid id or unauthorized')
  else:
    flash('Todo Deleted')
  return redirect(url_for('todos_page'))

@app.route('/logout', methods=['GET'])
@jwt_required()
def logout_action():
  flash('Logged Out')
  response = redirect(url_for('login_page'))
  unset_jwt_cookies(response)
  return response

@app.route('/admin')
@login_required(Admin)
def admin_page():
  page = request.args.get('page', 1, type=int)
  q = request.args.get('q', default='', type=str)
  done = request.args.get('done', default='any', type=str)
  todos = current_user.search_todos(q, done, page)
  return render_template('admin.html', todos=todos, q=q, page=page, done=done)


@app.route('/todo-stats', methods=["GET"])
@login_required(Admin)
def todo_stats():
  return jsonify(current_user.get_todo_stats())

@app.route('/stats')
@login_required(Admin)
def stats_page():
  return render_template('stats.html')

if __name__ == "__main__":
  app.run(host='0.0.0.0', port=81)
