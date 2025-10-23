# app.py
from flask import Flask, render_template, send_from_directory
import os

app = Flask(__name__)

# المسار الرئيسي (Home Route) لتقديم الصفحة الرئيسية (index.html)
@app.route('/')
def index():
    # يفترض أن ملف index.html موجود في مجلد templates
    return render_template('index.html')

# مسار لتقديم ملف tags.js الموجود في مجلد static
# ملاحظة: تم تسمية الدالة 'static_files' لاستخدامها في ملف index.html
@app.route('/static/<path:filename>')
def static_files(filename):
    # إرسال الملف المطلوب من مجلد static
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

# تهيئة التشغيل
if __name__ == '__main__':
    # التشغيل المحلي، يستخدم منفذ Heroku (PORT) إذا كان متاحاً
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

