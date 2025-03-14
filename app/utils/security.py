from flask import jsonify


def error_response(message, status_code=400):
    """Generate a standard error response"""
    return jsonify({"success": False, "message": message}), status_code


def success_response(data=None, message="Operation successful", status_code=200):
    """Generate a standard success response"""
    response = {"success": True, "message": message}
    if data is not None:
        response["data"] = data
    return jsonify(response), status_code
