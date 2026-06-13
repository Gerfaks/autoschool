from routes.admin_courses import register_admin_course_routes
from routes.admin_finance import register_admin_finance_routes
from routes.admin_people import register_admin_people_routes
from routes.admin_requests import register_admin_request_routes


def register_admin_routes(app):
    register_admin_people_routes(app)
    register_admin_course_routes(app)
    register_admin_finance_routes(app)
    register_admin_request_routes(app)
