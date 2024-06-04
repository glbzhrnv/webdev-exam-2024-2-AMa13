from flask_login import current_user

class CheckRole:
    def __init__(self, record=None):
        self.record = record
        
    def create(self):
        return current_user.is_admin()
    
    def show(self):
        return True
    
    def edit(self):
        if not self.record:
            return False
        if current_user.id == self.record['id']:
            return True
        is_admin = current_user.is_admin()
        is_moderator = current_user.is_moderator()
        return is_admin or is_moderator
    
    def delete(self):
        return current_user.is_admin()
