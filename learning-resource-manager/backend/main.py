import os
from flask import flask


def create_app():
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_mapping(
        SECRET_KEY='dev',
        DATABASE=os.path.join(app.instance_path, f"../database/{os.getenv('DATABASE_NAME')}"
    )
    
    os.makedirs(app.instance_path, exist_ok=True)

    @app.route("/test")
    def test():
        return "testing123"

    return app


def main():
   app = create_app()
   input()

if __name__ == "__main__":
    main()
