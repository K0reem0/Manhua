# -*- coding: utf-8 -*-
import os
import requests
import time
import json
from flask import Flask, jsonify, request, send_from_directory, Response

# الثوابت
MANGADEX_API_URL = "https://api.mangadex.org"
LIMIT_PER_PAGE = 20  # عدد النتائج التي يتم جلبها في كل طلب
PLACEHOLDER_URL = 'https://via.placeholder.com/250x350?text=No+Cover'

app = Flask(__name__)

# مسار الجذر لعرض ملف index.html
@app.route('/')
def index():
    """تقديم ملف index.html الرئيسي."""
    try:
        # افتراض أن index.html موجود في مجلد static
        return send_from_directory('static', 'index.html')
    except Exception as e:
        return f"Error serving index.html: {e}", 500

# مسار لتقديم الملفات الثابتة الأخرى (مثل tags.js)
@app.route('/static_files/<path:filename>')
def static_files(filename):
    """تقديم الملفات الثابتة مثل JavaScript."""
    # افتراض أن جميع الملفات الثابتة الأخرى موجودة أيضًا في مجلد static
    return send_from_directory('static', filename)

@app.route('/api/manhwa', methods=['GET'])
def get_manhwa_data():
    """نقطة نهاية لجلب بيانات المانهوا من MangaDex وتطبيق الفلاتر."""
    try:
        # 1. قراءة بارامترات الطلب من العميل
        initial_offset = request.args.get('offset', type=int, default=0)
        min_chapters = request.args.get('min_chapters', type=int, default=0)
        status = request.args.get('status', default='all')
        content_rating = request.args.get('content_rating', default='all')
        demographic = request.args.get('demographic', default='all')
        
        # استخدام getlist لاستقبال قائمة الـ IDs لتصنيفات (Tags)
        included_tags = request.args.getlist('includedTags[]')
        
        # متغيرات التحكم في الحلقة
        manhwa_list = []
        current_offset = initial_offset 
        total_manga_count = float('inf') 
        MAX_PAGES_TO_SCAN = 5 # الحد الأقصى للصفحات التي يمكن فحصها من MangaDex

        
        # حلقة لجلب ومعالجة النتائج حتى نصل للعدد المطلوب (LIMIT_PER_PAGE)
        for _ in range(MAX_PAGES_TO_SCAN):
            
            # إذا وصلنا للحد الأقصى للنتائج المطلوبة للعميل
            if len(manhwa_list) >= LIMIT_PER_PAGE:
                break
            
            # إذا تجاوزنا إجمالي عدد المانجا المتاح
            if current_offset >= total_manga_count:
                break
            
            # 2. بناء قائمة البارامترات (Key, Value) لطلب MangaDex
            # **هذا هو التصحيح الرئيسي لخطأ 400**، حيث يتم تمرير القائمة لضمان التكرار الصحيح
            
            query_params = []
            
            # بارامترات البحث الأساسية والثابتة
            query_params.append(('limit', LIMIT_PER_PAGE))
            query_params.append(('offset', current_offset))
            query_params.append(('order[followedCount]', 'desc'))
            query_params.append(('includes[]', 'cover_art'))
            query_params.append(('hasAvailableChapters', 'true'))
            
            # إضافة بارامترات الفلاتر الشرطية (status, rating, demographic)
            if status != 'all':
                query_params.append(('status[]', status))
            if content_rating != 'all':
                query_params.append(('contentRating[]', content_rating))
            if demographic != 'all':
                query_params.append(('publicationDemographic[]', demographic))
                
            # إضافة بارامترات التصنيفات (Tags)
            if included_tags:
                for tag_id in included_tags:
                    query_params.append(('includedTags[]', tag_id))


            # 3. إرسال الطلب إلى MangaDex
            manhwa_response = requests.get(f"{MANGADEX_API_URL}/manga", params=query_params, timeout=30)
            manhwa_response.raise_for_status() # رفع استثناء للردود 4xx/5xx

            manhwa_data = manhwa_response.json()
            total_manga_count = manhwa_data.get('total', 0)
            
            # 4. معالجة النتائج المستلمة وتطبيق فلتر الفصول محلياً
            for manga in manhwa_data.get('data', []):
                manga_id = manga['id']
                chapters_num = 0

                # جلب عدد الفصول باستخدام aggregation
                try:
                    agg_response = requests.get(f"{MANGADEX_API_URL}/manga/{manga_id}/aggregate", params={'translatedLanguage[]': 'en'}, timeout=15)
                    agg_response.raise_for_status()
                    agg_data = agg_response.json()
                    volumes = agg_data.get('volumes', {})
                    
                    # حساب أعلى رقم فصل متاح
                    if isinstance(volumes, dict):
                        for vol_data in volumes.values():
                            chapters = vol_data.get('chapters', {})
                            if isinstance(chapters, dict):
                                chapters_num = max(
                                    chapters_num,
                                    max(
                                        (float(chap_data.get('chapter', 0)) for chap_data in chapters.values() if chap_data.get('chapter')),
                                        default=0
                                    )
                                )
                except requests.RequestException as e:
                    # طباعة تحذير وعدم مقاطعة التنفيذ
                    print(f"Warning: Failed to fetch aggregate for {manga_id}: {e}")
                    pass 

                # فلتر الحد الأدنى للفصول (يُطبق محلياً)
                if min_chapters > 0 and chapters_num < min_chapters:
                    continue 

                # 5. تجهيز بيانات المانهوا (الصور، العناوين، التصنيفات)
                cover_url = PLACEHOLDER_URL
                cover_art = next((rel for rel in manga.get('relationships', []) if rel.get('type') == 'cover_art'), None)
                if cover_art:
                    file_name = cover_art.get('attributes', {}).get('fileName')
                    if file_name:
                        # إنشاء مسار للـ Proxy على الخادم المحلي
                        cover_url = f"/cover/{initial_offset}/{manga_id}/{file_name}"

                title_en = manga['attributes'].get('title', {}).get('en')
                # استخدام أول عنوان متاح إذا لم يكن العنوان الإنجليزي موجودًا
                if not title_en:
                    title_val = next(iter(manga['attributes'].get('title', {}).values()), 'Unknown Title')
                else:
                    title_val = title_en

                # استخراج أسماء التصنيفات بالإنجليزية
                genres_list = [tag['attributes']['name']['en'] for tag in manga.get('attributes', {}).get('tags', [])
                               if tag['attributes']['group'] == 'genre' and 'en' in tag['attributes']['name']]
                
                demographic_val = manga['attributes'].get('publicationDemographic', 'none')
                content_rating_val = manga['attributes'].get('contentRating', 'safe')

                manhwa_list.append({
                    'id': manga_id,
                    'title': title_val,
                    'cover': cover_url,
                    'chapters': str(int(chapters_num)) if chapters_num > 0 else 'غير معروف',
                    'chaptersNum': chapters_num,
                    'status': manga['attributes'].get('status'),
                    'genres': genres_list,
                    # تقييم افتراضي
                    'rating': manga['attributes'].get('averageRating', 0), 
                    'description': manga['attributes'].get('description', {}).get('en'),
                    'demographic': demographic_val,
                    'contentRating': content_rating_val
                })
                
                if len(manhwa_list) >= LIMIT_PER_PAGE:
                    break
            
            # 6. تحديث الأوفست والانتقال للصفحة التالية من MangaDex
            current_offset += LIMIT_PER_PAGE
            
            # إضافة تأخير بسيط لمنع حظر IP من MangaDex
            time.sleep(0.1) 


        # 7. إرجاع النتائج التي تم تجميعها للعميل
        new_offset = initial_offset + len(manhwa_list)
        # تحديد ما إذا كان هناك المزيد من النتائج بناءً على عدد النتائج المستلمة
        has_more = len(manhwa_list) == LIMIT_PER_PAGE
        
        return jsonify({
            'data': manhwa_list,
            'total': total_manga_count,
            'limit': LIMIT_PER_PAGE,
            'offset': new_offset,
            'hasMore': has_more
        })

    except requests.exceptions.RequestException as e:
        error_status = e.response.status_code if e.response is not None else 503
        error_details = f"MangaDex API failed: {error_status}. Check server logs for details."
        print(f"Error fetching data from MangaDex: {error_details}")
        # إرجاع رسالة خطأ واضحة
        return jsonify({'error': 'Failed to fetch data from external API.', 'details': error_details}), error_status
    except Exception as e:
        error_message = f"An unexpected internal server error occurred: {e}"
        print(error_message)
        return jsonify({'error': 'An internal server error occurred.', 'details': error_message}), 500


@app.route('/cover/<int:request_offset>/<manga_id>/<filename>')
def get_cover_image(request_offset, manga_id, filename):
    """نقطة نهاية لتقديم صور الغلاف عبر الخادم (Proxy)."""
    
    # بناء URL الصورة الأصلية بجودة 512 بكسل
    image_url = f"https://uploads.mangadex.org/covers/{manga_id}/{filename}.512.jpg"
    
    try:
        # طلب الصورة من MangaDex
        image_response = requests.get(image_url, stream=True, timeout=15)
        image_response.raise_for_status()
        
        # استخراج نوع المحتوى وإرجاع الصورة كاستجابة خام (Response)
        content_type = image_response.headers.get('Content-Type', 'image/jpeg')
        return Response(image_response.iter_content(chunk_size=8192),
                        mimetype=content_type,
                        status=200)
    except requests.RequestException as e:
        print(f"Error proxying cover image {image_url}: {e}")
        # إرجاع صورة بديلة أو خطأ 404
        return jsonify({'error': 'Image not found or failed to proxy'}), 404

if __name__ == '__main__':
    # الحصول على المنفذ من متغيرات البيئة (عادةً 5000)
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
