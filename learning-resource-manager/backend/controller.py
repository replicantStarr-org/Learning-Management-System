from flask import Blueprint

def main():
    bp = Blueprint('api', __name__)

    @bp.route('/tesing', methods=['GET']):
        return 'testing'

if __name__ == "__main__":
    main()
