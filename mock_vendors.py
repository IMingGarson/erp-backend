from django.contrib.auth.models import User

from factory.models import Vendor

mock_data = [
    {
        "name": "開元食品工業股份有限公司",
        "tax_id": "20873130",
        "address": "台北市內湖區民善街83號",
        "phone": "0800-020-368",
        "contact_person": "林先生",
    },
    {
        "name": "大成長城企業股份有限公司",
        "tax_id": "73030739",
        "address": "台南市永康區蔦松二街3號",
        "phone": "06-253-1111",
        "contact_person": "陳小姐",
    },
    {
        "name": "台灣卜蜂企業股份有限公司",
        "tax_id": "05022061",
        "address": "台北市中山區松江路87號",
        "phone": "02-2507-7071",
        "contact_person": "王經理",
    },
    {
        "name": "德麥食品股份有限公司",
        "tax_id": "23396860",
        "address": "新北市五股區五權五路31號",
        "phone": "02-2298-1347",
        "contact_person": "張先生",
    },
    {
        "name": "聯華製粉食品股份有限公司",
        "tax_id": "83457111",
        "address": "桃園市楊梅區民富路三段647號",
        "phone": "03-472-2121",
        "contact_person": "許小姐",
    },
    {
        "name": "桂冠實業股份有限公司",
        "tax_id": "04415802",
        "address": "台北市中正區羅斯福路三段126號",
        "phone": "02-2365-5222",
        "contact_person": "吳先生",
    },
    {
        "name": "銘珍食品廠有限公司",
        "tax_id": "33075253",
        "address": "新北市淡水區中正東路二段69之5號",
        "phone": "02-2809-1155",
        "contact_person": "黃小姐",
    },
    {
        "name": "嘉一香食品股份有限公司",
        "tax_id": "22650080",
        "address": "新北市樹林區柑園街二段122巷12號",
        "phone": "02-2680-2188",
        "contact_person": "周經理",
    },
    {
        "name": "聯夏食品工業股份有限公司",
        "tax_id": "04313264",
        "address": "台北市中正區仁愛路一段59號",
        "phone": "02-2393-3366",
        "contact_person": "李先生",
    },
    {
        "name": "茂林食品股份有限公司",
        "tax_id": "16781200",
        "address": "台中市西屯區工業區三十一路29號",
        "phone": "04-2359-2288",
        "contact_person": "趙小姐",
    },
]

rd_user = User.objects.filter(username="rd_user").first()
for item in mock_data:
    Vendor.objects.get_or_create(
        tax_id=item["tax_id"],
        defaults={
            "name": item["name"],
            "address": item["address"],
            "phone": item["phone"],
            "contact_person": item["contact_person"],
        },
        created_by=rd_user,
    )

print("10 家食品批發商 Mock Data 建立完成！")
