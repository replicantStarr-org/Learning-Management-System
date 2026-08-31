import os
from flask import Flask
from controllers.resources_controller import resources_bp 

def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, f"../database/{os.getenv('DATABASE_NAME')}")
    )
    
    os.makedirs(app.instance_path, exist_ok=True)

    @app.route("/test")
    def test():
        return "testing123"

    return app

def register_blueprints(app):
    app.register_blueprint(resources_bp, url_prefix='/api')

def main():
   app = create_app()
   register_blueprints(app)

if __name__ == "__main__":
    main()
