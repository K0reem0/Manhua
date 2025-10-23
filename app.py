# app.py
from flask import Flask, render_template, send_from_directory, request, jsonify
import os
import requests 

app = Flask(__name__)

MANGADEX_API_URL = "https://api.mangadex.org"
LIMIT_PER_PAGE = 100

# المسارات الأساسية (كما هي)
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(os.path.join(app.root_path, 'static'), filename)

# نقطة النهاية المحدثة لجلب بيانات المانهوا
@app.route('/api/manhwa', methods=['GET'])
def get_manhwa_data():
    try:
        # 1. جمع الفلاتر من طلب المتصفح
        offset = request.args.get('offset', type=int, default=0)
        min_chapters = request.args.get('min_chapters', type=int, default=0)
        status = request.args.get('status', default='all')
        content_rating = request.args.get('content_rating', default='all')
        demographic = request.args.get('demographic', default='all')
        included_tags = request.args.getlist('includedTags[]')

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
        manhwa_response.raise_for_status()

        manhwa_data = manhwa_response.json()
        manhwa_list = []
        
        for manga in manhwa_data.get('data', []):
            manga_id = manga['id']
            chapters_num = 0
            
            # جلب الفصول (Aggregate)
            try:
                agg_response = requests.get(f"{MANGADEX_API_URL}/manga/{manga_id}/aggregate", 
                                            params={'translatedLanguage[]': 'en'})
                agg_response.raise_for_status()
                agg_data = agg_response.json()
                
                # *** منطقة التصحيح لخطأ 'list' object has no attribute 'values' ***
                volumes = agg_data.get('volumes', {})
                if isinstance(volumes, dict):
                    for vol_data in volumes.values(): 
                        chapters = vol_data.get('chapters', {})
                        if isinstance(chapters, dict):
                            for chap_data in chapters.values():
                                try:
                                    # قراءة الفصل كـ float لتحصل على أعلى رقم بغض النظر عن الأجزاء
                                    chapter_num = float(chap_data.get('chapter', 0))
                                    if chapter_num > chapters_num:
                                        chapters_num = chapter_num
                                except (ValueError, TypeError):
                                    pass
                # ***************************************************************

            except requests.RequestException as e:
                print(f"Warning: Failed to fetch aggregate for {manga_id}: {e}")
            
            # 5. تطبيق فلتر الحد الأدنى للفصول (Python-Side Filtering)
            if min_chapters > 0 and chapters_num < min_chapters:
                continue

            # استخراج بيانات الغلاف
            cover_url = 'https://via.placeholder.com/250x350?text=No+Cover'
            cover_art = next((rel for rel in manga.get('relationships', []) if rel['type'] == 'cover_art'), None)
            if cover_art:
                file_name = cover_art.get('attributes', {}).get('fileName')
                if file_name:
                    cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{file_name}.256.jpg"

            # استخراج العنوان
            title_en = manga['attributes'].get('title', {}).get('en')
            # إذا لم يوجد عنوان إنجليزي، نأخذ أول عنوان متاح
            if not title_en:
                title_data = manga['attributes'].get('title', {})
                title_val = next(iter(title_data.values()), 'Unknown Title')
            else:
                title_val = title_en

            # استخراج التصنيفات والميتا
            genres_list = [tag['attributes']['name']['en'] for tag in manga.get('attributes', {}).get('tags', []) 
                           if tag['attributes']['group'] == 'genre' and 'en' in tag['attributes']['name']]
            demographic_val = manga['attributes'].get('publicationDemographic', 'none')
            content_rating_val = manga['attributes'].get('contentRating', 'safe')

            # إضافة المانهوا المفلترة والجاهزة
            manhwa_list.append({
                'id': manga_id,
                'title': title_val,
                'cover': cover_url,
                'chapters': str(int(chapters_num)) if chapters_num > 0 else 'غير معروف', # عرض رقم صحيح
                'chaptersNum': chapters_num,
                'status': manga['attributes'].get('status'),
                'genres': genres_list,
                'rating': manga['attributes'].get('averageRating'),
                'description': manga['attributes'].get('description', {}).get('en'),
                'demographic': demographic_val,
                'contentRating': content_rating_val
            })
            
        # 6. إرجاع النتيجة
        # حساب الأوفست الجديد بشكل صحيح
        new_offset = offset + len(manhwa_data.get('data', []))
        
        return jsonify({
            'data': manhwa_list,
            'total': manhwa_data.get('total', 0),
            'limit': LIMIT_PER_PAGE,
            'offset': new_offset, 
            'hasMore': manhwa_data.get('total', 0) > new_offset
        })

    except requests.exceptions.RequestException as e:
        # خطأ في الاتصال الخارجي
        error_status = e.response.status_code if e.response is not None else 503
        error_details = f"MangaDex API failed: {error_status}. Details: {e}"
        print(f"Error fetching data from MangaDex: {error_details}")
        return jsonify({'error': 'Failed to fetch data from external API.', 'details': error_details}), error_status
    except Exception as e:
        # معالجة الأخطاء العامة الأخرى
        error_message = f"An unexpected error occurred: '{e}'"
        print(error_message)
        return jsonify({'error': 'An internal server error occurred.', 'details': error_message}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
