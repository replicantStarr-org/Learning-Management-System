import os
from flask import Flask
from controllers.resources_controller import resources_bp 
from controllers.highlights_controller import highlights_bp
from controllers.subjects_controller import subjects_bp
from controllers.chat_controller import chat_bp

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    register_blueprints(app)
    return app

def register_blueprints(app):
    app.register_blueprint(resources_bp, url_prefix='/api/resources')
    app.register_blueprint(subjects_bp, url_prefix='/api/subjects')
    app.register_blueprint(highlights_bp, url_prefix='/api/highlights')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')

app = create_app()

def main():
   app.run(host='0.0.0.0', port=5000, threaded=True)

if __name__ == "__main__":
    main()
