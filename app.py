from flask import Flask, render_template, send_from_directory, request, jsonify
import os
import requests 

app = Flask(__name__)

MANGADEX_API_URL = "https://api.mangadex.org"
LIMIT_PER_PAGE = 20

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
            'includes[]': 'cover_art', # تأكيد تضمين الغلاف
            'hasAvailableChapters': 'true',
            'translatedLanguage[]': ['en'] # فلترة للغات المترجمة المتاحة
        }
        
        # **التعديل الأول والحيوي لحل مشكلة 400 Bad Request**
        # يجب تمرير contentRating[] دائمًا. إذا كانت 'all'، نرسل جميع القيم المقبولة.
        if content_rating != 'all':
             params['contentRating[]'] = [content_rating]
        else:
             # إذا لم يتم تحديد فلتر، نطلب كل التصنيفات المقبولة (MangaDex تتطلب هذا في بعض الحالات)
             params['contentRating[]'] = ['safe', 'suggestive', 'erotica', 'pornographic']


        # تطبيق الفلاتر الأخرى
        if status != 'all':
            params['status[]'] = [status]
        
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
            
            # 4. جلب الفصول (Aggregate)
            try:
                # طلب الفصول
                agg_response = requests.get(f"{MANGADEX_API_URL}/manga/{manga_id}/aggregate", 
                                            params={'translatedLanguage[]': 'en'})
                agg_response.raise_for_status()
                agg_data = agg_response.json()
                
                # حساب أعلى رقم فصل 
                volumes = agg_data.get('volumes', {})
                if isinstance(volumes, dict):
                    for vol_data in volumes.values(): 
                        chapters = vol_data.get('chapters', {})
                        if isinstance(chapters, dict):
                            for chap_data in chapters.values():
                                try:
                                    chapter_num = float(chap_data.get('chapter', 0))
                                    if chapter_num > chapters_num:
                                        chapters_num = chapter_num
                                except (ValueError, TypeError):
                                    pass
            except requests.RequestException as e:
                # إهمال المانهوا التي تفشل في جلب الفصول الخاصة بها
                print(f"Warning: Failed to fetch aggregate for {manga_id}: {e}")
                
            
            # 5. تطبيق فلتر الحد الأدنى للفصول (Python-Side Filtering)
            if min_chapters > 0 and chapters_num < min_chapters:
                continue

            # 6. استخراج وتصحيح رابط الغلاف (التعديل الثاني لحل مشكلة الصور)
            cover_url = 'https://via.placeholder.com/250x350?text=No+Cover'
            cover_art = next((rel for rel in manga.get('relationships', []) if rel.get('type') == 'cover_art'), None)
            
            if cover_art:
                cover_attributes = cover_art.get('attributes')
                if cover_attributes and isinstance(cover_attributes, dict):
                    file_name = cover_attributes.get('fileName')
                    if file_name:
                        # يجب إزالة الامتداد الأصلي (.jpg) قبل إضافة لاحقة الحجم (.256.jpg)
                        # نستخدم os.path.splitext للحصول على اسم الملف بدون امتداد.
                        base_file_name = os.path.splitext(file_name)[0]
                        # الرابط الصحيح الآن
                        cover_url = f"https://uploads.mangadex.org/covers/{manga_id}/{base_file_name}.256.jpg"


            # 7. استخراج العنوان
            title_en = manga['attributes'].get('title', {}).get('en')
            if not title_en:
                title_data = manga['attributes'].get('title', {})
                title_val = next(iter(title_data.values()), 'Unknown Title')
            else:
                title_val = title_en

            # 8. استخراج التصنيفات والميتا
            genres_list = [tag['attributes']['name']['en'] for tag in manga.get('attributes', {}).get('tags', []) 
                           if tag['attributes']['group'] == 'genre' and 'en' in tag['attributes']['name']]
            demographic_val = manga['attributes'].get('publicationDemographic', 'none')
            content_rating_val = manga['attributes'].get('contentRating', 'safe')

            # إضافة المانهوا المفلترة والجاهزة
            manhwa_list.append({
                'id': manga_id,
                'title': title_val,
                'cover': cover_url,
                'chapters': str(int(chapters_num)) if chapters_num > 0 else 'غير معروف',
                'chaptersNum': chapters_num,
                'status': manga['attributes'].get('status'),
                # تم تعيين rating إلى None لأنها لم تعد مُعادة بشكل موثوق في هذا المسار
                'rating': None, 
                'genres': genres_list,
                'description': manga['attributes'].get('description', {}).get('en'),
                'demographic': demographic_val,
                'contentRating': content_rating_val
            })
            
        # 9. إرجاع النتيجة
        new_offset = offset + len(manhwa_data.get('data', []))
        
        return jsonify({
            'data': manhwa_list,
            'total': manhwa_data.get('total', 0),
            'limit': LIMIT_PER_PAGE,
            'offset': new_offset, 
            'hasMore': manhwa_data.get('total', 0) > new_offset
        })

    except requests.exceptions.RequestException as e:
        # خطأ في الاتصال الخارجي (MangaDex)
        error_status = e.response.status_code if e.response is not None else 503
        # عرض الرابط الذي أرسله Flask للمساعدة في التصحيح
        error_details = f"MangaDex API failed: {error_status}. Check network or API availability. Request URL: {manhwa_response.url if 'manhwa_response' in locals() else 'N/A'}"
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
