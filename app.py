# app.py
from flask import Flask, render_template, send_from_directory, request, jsonify
import os
import requests # سنستخدم هذه المكتبة لجلب البيانات من API MangaDex

app = Flask(__name__)

MANGADEX_API_URL = "https://api.mangadex.org"
LIMIT_PER_PAGE = 100

# المسار الرئيسي لتقديم الصفحة الرئيسية (index.html)
@app.route('/')
def index():
    return render_template('index.html')

# مسار لخدمة ملفات الـ static (مثل tags.js)
@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

# نقطة النهاية الجديدة لجلب بيانات المانهوا
@app.route('/api/manhwa', methods=['GET'])
def get_manhwa_data():
    try:
        # 1. جمع الفلاتر من طلب المتصفح (Query Parameters)
        offset = request.args.get('offset', type=int, default=0)
        min_chapters = request.args.get('min_chapters', type=int, default=0)
        status = request.args.get('status', default='all')
        content_rating = request.args.get('content_rating', default='all')
        demographic = request.args.get('demographic', default='all')
        included_tags = request.args.getlist('includedTags[]') # الحصول على قائمة التصنيفات

        # 2. بناء البارامترات لـ MangaDex API
        params = {
            'limit': LIMIT_PER_PAGE,
            'offset': offset,
            'order[followedCount]': 'desc',
            'includes[]': 'cover_art',
            'hasAvailableChapters': 'true'
        }

        # تطبيق الفلاتر
        if status != 'all':
            params['status[]'] = [status]
        if content_rating != 'all':
            params['contentRating[]'] = [content_rating]
        if demographic != 'all':
            params['publicationDemographic[]'] = [demographic]
        if included_tags:
            params['includedTags[]'] = included_tags
        
        # 3. جلب البيانات الأساسية من MangaDex
        manhwa_response = requests.get(f"{MANGADEX_API_URL}/manga", params=params)
        manhwa_response.raise_for_status() # إلقاء خطأ لأكواد الحالة 4xx/5xx

        manhwa_data = manhwa_response.json()
        manhwa_list = []
        
        # 4. جلب تفاصيل الفصول (Aggregate) لكل مانجوا
        
        # يجب جمع جميع الـ IDs لعمل طلب جماعي للفصول إذا أمكن، 
        # لكن MangaDex لا تدعم Aggregate جماعيًا، لذا سنعتمد على الطلبات الفردية
        
        for manga in manhwa_data.get('data', []):
            manga_id = manga['id']
            chapters_num = 0
            
            # جلب الفصول
            try:
                agg_response = requests.get(f"{MANGADEX_API_URL}/manga/{manga_id}/aggregate", 
                                            params={'translatedLanguage[]': 'en'})
                agg_response.raise_for_status()
                agg_data = agg_response.json()
                
                # حساب أعلى رقم فصل
                for vol_data in agg_data.get('volumes', {}).values():
                    for chap_data in vol_data.get('chapters', {}).values():
                        try:
                            chapter_num = float(chap_data.get('chapter', 0))
                            if chapter_num > chapters_num:
                                chapters_num = chapter_num
                        except ValueError:
                            pass # تجاهل الفصول غير الرقمية
            except requests.RequestException as e:
                print(f"Warning: Failed to fetch aggregate for {manga_id}: {e}")
            
            # 5. تطبيق فلتر الحد الأدنى للفصول (Python-Side Filtering)
            if min_chapters > 0 and chapters_num < min_chapters:
                continue # تخطي المانهوا التي لا تحقق الشرط

            # استخراج بيانات الغلاف
            cover_url = 'https://via.placeholder.com/250x350?text=No+Cover'
            cover_art = next((rel for rel in manga.get('relationships', []) if rel['type'] == 'cover_art'), None)
            if cover_art:
                file_name = cover_art.get('attributes', {}).get('fileName')
                if file_name:
                    cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{file_name}.256.jpg"

            # استخراج التصنيفات (Genres) والميتا
            genres_list = [tag['attributes']['name']['en'] for tag in manga.get('attributes', {}).get('tags', []) if tag['attributes']['group'] == 'genre' and 'en' in tag['attributes']['name']]
            demographic_val = manga['attributes'].get('publicationDemographic', 'none')
            content_rating_val = manga['attributes'].get('contentRating', 'safe')

            # إضافة المانهوا المفلترة والجاهزة
            manhwa_list.append({
                'id': manga_id,
                'title': manga['attributes'].get('title', {}).get('en') or next(iter(manga['attributes'].get('title', {}).values()), 'Unknown Title'),
                'cover': cover_url,
                'chapters': str(chapters_num) if chapters_num > 0 else 'غير معروف',
                'chaptersNum': chapters_num,
                'status': manga['attributes'].get('status'),
                'genres': genres_list,
                'rating': manga['attributes'].get('averageRating'),
                'description': manga['attributes'].get('description', {}).get('en'),
                'demographic': demographic_val,
                'contentRating': content_rating_val
            })
            
        # 6. إرجاع النتيجة
        return jsonify({
            'data': manhwa_list,
            'total': manhwa_data.get('total', 0),
            'limit': LIMIT_PER_PAGE,
            'offset': offset + len(manhwa_data.get('data', [])), # الأوفست الجديد
            'hasMore': manhwa_data.get('total', 0) > (offset + len(manhwa_data.get('data', [])))
        })

    except requests.exceptions.RequestException as e:
        # معالجة أخطاء الاتصال بالسيرفر الخارجي (MangaDex)
        print(f"Error fetching data from MangaDex: {e}")
        return jsonify({'error': 'Failed to fetch data from external API.', 'details': str(e)}), 503
    except Exception as e:
        # معالجة الأخطاء العامة
        print(f"An unexpected error occurred: {e}")
        return jsonify({'error': 'An internal server error occurred.'}), 500

# تهيئة التشغيل
if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
