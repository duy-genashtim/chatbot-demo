"""Generate sample customer service PDF (Vietnamese) for chatbot RAG corpus.

Usage:
  cd chatbotv2/backend && .venv/Scripts/python.exe scripts/generate_cskh_pdf.py
Output: chatbotv2/backend/data/cskh-tech-store.pdf
"""

from pathlib import Path

from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
)

# Register Arial (Windows) for Vietnamese diacritics
pdfmetrics.registerFont(TTFont("Arial", "C:/Windows/Fonts/arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))

styles = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=styles["Heading1"], fontName="Arial-Bold", fontSize=18, spaceAfter=12, textColor="#253956")
H2 = ParagraphStyle("H2", parent=styles["Heading2"], fontName="Arial-Bold", fontSize=13, spaceBefore=10, spaceAfter=6, textColor="#253956")
P = ParagraphStyle("P", parent=styles["BodyText"], fontName="Arial", fontSize=11, leading=16, alignment=TA_JUSTIFY, spaceAfter=6)
LI = ParagraphStyle("LI", parent=P, leftIndent=14, bulletIndent=2)


def section(title: str, paragraphs: list[str | tuple[str, list[str]]]):
    out = [Paragraph(title, H2)]
    for item in paragraphs:
        if isinstance(item, str):
            out.append(Paragraph(item, P))
        else:
            intro, bullets = item
            if intro:
                out.append(Paragraph(intro, P))
            for b in bullets:
                out.append(Paragraph(f"&bull; {b}", LI))
    return out


# ── Page 1: Giới thiệu ────────────────────────────────────────────────
page1 = [
    Paragraph("CẨM NANG CHĂM SÓC KHÁCH HÀNG", H1),
    Paragraph("Sàn Thương Mại Điện Tử TechStore - Chuyên Đồ Điện Tử", H2),
    Spacer(1, 6),

    *section("1. Giới thiệu trợ lý CSKH", [
        "Xin chào! Tôi là trợ lý chăm sóc khách hàng ảo của TechStore - sàn thương mại điện tử "
        "chuyên cung cấp các sản phẩm đồ điện tử chính hãng tại Việt Nam. Tôi được thiết kế để hỗ trợ "
        "khách hàng 24/7 với mọi câu hỏi về sản phẩm, đơn hàng, bảo hành, đổi trả và các chính sách của TechStore.",

        "Tên đầy đủ của tôi là <b>TechBot</b>. Tôi không phải là người thật mà là một chatbot AI "
        "được huấn luyện dựa trên kho tài liệu chính sách và FAQ của công ty. Mọi thông tin tôi cung cấp "
        "đều dựa trên tài liệu chính thức được TechStore cập nhật thường xuyên.",
    ]),

    *section("2. Tôi có thể giúp gì cho bạn?", [
        ("Tôi có thể hỗ trợ bạn các vấn đề sau:", [
            "Tư vấn sản phẩm điện tử: điện thoại, laptop, máy tính bảng, tai nghe, đồng hồ thông minh, phụ kiện",
            "Hướng dẫn đặt hàng, thanh toán và theo dõi đơn hàng",
            "Giải đáp chính sách bảo hành, đổi trả, hoàn tiền",
            "Thông tin về phí vận chuyển và thời gian giao hàng",
            "Hướng dẫn sử dụng mã giảm giá, voucher, chương trình khuyến mãi",
            "Hỗ trợ khiếu nại, phản hồi về dịch vụ",
            "Hướng dẫn đăng ký tài khoản, quên mật khẩu, bảo mật",
        ]),
        "Nếu câu hỏi của bạn vượt ngoài phạm vi tài liệu của tôi, vui lòng liên hệ tổng đài "
        "<b>1900 1234</b> hoặc gửi email tới <b>cskh@techstore.vn</b> để được nhân viên hỗ trợ trực tiếp.",
    ]),

    *section("3. Danh mục sản phẩm chính", [
        ("TechStore phân phối chính hãng các nhóm sản phẩm:", [
            "Điện thoại di động: iPhone, Samsung Galaxy, Xiaomi, OPPO, Vivo, Realme",
            "Laptop & PC: Apple MacBook, Dell, HP, Lenovo, ASUS, Acer, MSI",
            "Máy tính bảng: iPad, Samsung Tab, Xiaomi Pad, Huawei MatePad",
            "Âm thanh: Tai nghe AirPods, Sony, Bose, JBL, loa Bluetooth",
            "Đồng hồ thông minh: Apple Watch, Samsung Galaxy Watch, Garmin, Xiaomi Mi Band",
            "Phụ kiện: Sạc, cáp, ốp lưng, bao da, thẻ nhớ, ổ cứng di động",
        ]),
    ]),

    PageBreak(),
]

# ── Page 2: Đặt hàng & Thanh toán ─────────────────────────────────────
page2 = [
    *section("4. Hướng dẫn đặt hàng", [
        ("Khách hàng có thể đặt hàng theo 3 cách:", [
            "Đặt hàng trực tuyến tại website techstore.vn - hoạt động 24/7",
            "Đặt hàng qua ứng dụng TechStore Mobile trên iOS và Android",
            "Đặt hàng qua hotline 1900 1234 từ 8:00 đến 22:00 mỗi ngày",
        ]),
        ("Quy trình đặt hàng online gồm 5 bước:", [
            "Bước 1: Chọn sản phẩm và thêm vào giỏ hàng",
            "Bước 2: Vào giỏ hàng, kiểm tra sản phẩm và số lượng",
            "Bước 3: Điền thông tin nhận hàng (họ tên, số điện thoại, địa chỉ)",
            "Bước 4: Chọn phương thức thanh toán và vận chuyển",
            "Bước 5: Xác nhận đơn hàng - hệ thống gửi mã đơn qua SMS và email",
        ]),
    ]),

    *section("5. Phương thức thanh toán", [
        ("TechStore hỗ trợ đa dạng phương thức thanh toán:", [
            "Thanh toán khi nhận hàng (COD) - áp dụng toàn quốc, đơn dưới 20 triệu",
            "Chuyển khoản ngân hàng: Vietcombank, Techcombank, BIDV, ACB, MB Bank",
            "Thẻ tín dụng/ghi nợ quốc tế: Visa, Mastercard, JCB, American Express",
            "Ví điện tử: MoMo, ZaloPay, VNPay, ShopeePay",
            "Trả góp 0% qua thẻ tín dụng các ngân hàng đối tác (kỳ hạn 3, 6, 9, 12 tháng)",
            "Trả góp qua công ty tài chính: Home Credit, FE Credit, HD Saison",
        ]),
        "Đối với đơn hàng giá trị từ 20 triệu trở lên, khách hàng cần thanh toán trước hoặc trả góp, "
        "không áp dụng COD để đảm bảo an toàn giao dịch.",
    ]),

    *section("6. Vận chuyển và giao hàng", [
        ("Thời gian giao hàng dự kiến:", [
            "Nội thành Hà Nội, TP.HCM, Đà Nẵng: 2 đến 4 giờ (giao hàng nhanh) hoặc trong ngày",
            "Các tỉnh thành phố khác: 1 đến 3 ngày làm việc",
            "Khu vực miền núi, hải đảo: 3 đến 7 ngày làm việc",
        ]),
        ("Phí vận chuyển:", [
            "Miễn phí vận chuyển cho đơn hàng từ 500.000 VNĐ trở lên",
            "Đơn hàng dưới 500.000 VNĐ: phí từ 20.000 đến 50.000 VNĐ tùy khu vực",
            "Giao hàng nhanh nội thành: phụ thu 30.000 VNĐ",
            "Giao hàng siêu tốc 2 giờ: phụ thu 50.000 VNĐ",
        ]),
        "Khách hàng có thể theo dõi đơn hàng theo thời gian thực qua mục <b>Đơn hàng của tôi</b> "
        "trên website hoặc ứng dụng, hoặc nhập mã đơn tại trang techstore.vn/tracking.",
    ]),

    PageBreak(),
]

# ── Page 3: Bảo hành & Đổi trả ────────────────────────────────────────
page3 = [
    *section("7. Chính sách bảo hành", [
        ("TechStore áp dụng chính sách bảo hành chính hãng cho tất cả sản phẩm:", [
            "Điện thoại, máy tính bảng: bảo hành 12 tháng tại trung tâm bảo hành chính hãng",
            "Laptop, PC: bảo hành 12 đến 24 tháng tùy nhà sản xuất",
            "Tai nghe, loa, phụ kiện âm thanh: bảo hành 6 đến 12 tháng",
            "Đồng hồ thông minh: bảo hành 12 tháng",
            "Phụ kiện (sạc, cáp, ốp): bảo hành 3 đến 6 tháng",
        ]),
        ("Điều kiện bảo hành:", [
            "Sản phẩm còn tem bảo hành nguyên vẹn, không rách, không tẩy xóa",
            "Còn phiếu bảo hành hoặc hóa đơn mua hàng từ TechStore",
            "Lỗi do nhà sản xuất, không phải do va đập, vào nước, cháy nổ, sét đánh",
            "Sản phẩm chưa từng được sửa chữa bởi đơn vị không được ủy quyền",
        ]),
        "Thời gian sửa chữa bảo hành thông thường từ 7 đến 14 ngày làm việc. Trong thời gian "
        "chờ sửa, TechStore có chính sách cho mượn máy tạm thời với một số dòng sản phẩm cao cấp.",
    ]),

    *section("8. Chính sách đổi trả", [
        ("Khách hàng được đổi hoặc trả sản phẩm trong các trường hợp:", [
            "Đổi trả miễn phí trong 7 ngày kể từ khi nhận hàng nếu sản phẩm có lỗi từ nhà sản xuất",
            "Đổi sang sản phẩm khác trong 30 ngày nếu sản phẩm còn nguyên seal, chưa kích hoạt, đầy đủ phụ kiện",
            "Trả hàng và hoàn tiền 100% nếu giao sai sản phẩm so với đơn hàng",
            "Hoàn tiền nếu sản phẩm hết hàng và không có giải pháp thay thế phù hợp",
        ]),
        ("Quy trình đổi trả:", [
            "Bước 1: Liên hệ hotline 1900 1234 hoặc chat với CSKH trong vòng 7 ngày",
            "Bước 2: Cung cấp mã đơn hàng, mô tả lỗi, gửi ảnh hoặc video minh chứng",
            "Bước 3: Nhân viên TechStore xác nhận và sắp xếp nhận lại sản phẩm tận nơi",
            "Bước 4: Sau khi kiểm tra, TechStore sẽ đổi sản phẩm mới hoặc hoàn tiền trong 3 đến 7 ngày",
        ]),
        "Hình thức hoàn tiền: chuyển khoản ngân hàng, hoàn vào ví TechStore, hoặc hoàn vào thẻ tín dụng "
        "đã thanh toán (đối với giao dịch online).",
    ]),

    PageBreak(),
]

# ── Page 4: Khuyến mãi, tài khoản, liên hệ ────────────────────────────
page4 = [
    *section("9. Khuyến mãi và mã giảm giá", [
        ("TechStore thường xuyên có các chương trình khuyến mãi:", [
            "Flash Sale hằng ngày từ 12:00 đến 14:00 và từ 20:00 đến 22:00",
            "Siêu sale ngày đôi: 1/1, 2/2, 3/3 đến 12/12 hằng tháng",
            "Khuyến mãi sinh nhật: tặng voucher 200.000 VNĐ cho khách hàng thân thiết",
            "Chương trình tích điểm: 1.000 VNĐ = 1 điểm, đổi điểm lấy voucher hoặc quà",
            "Ưu đãi sinh viên: giảm thêm 5% cho học sinh, sinh viên có thẻ hợp lệ",
        ]),
        "Để áp dụng mã giảm giá, khách hàng nhập mã tại bước thanh toán. Mỗi đơn hàng chỉ áp dụng "
        "1 mã, mã không cộng dồn với chương trình giảm giá khác trừ khi có ghi chú đặc biệt.",
    ]),

    *section("10. Tài khoản và bảo mật", [
        ("Lợi ích khi đăng ký tài khoản TechStore:", [
            "Lưu địa chỉ giao hàng, phương thức thanh toán cho lần mua sau",
            "Theo dõi lịch sử đơn hàng, trạng thái giao hàng",
            "Tích điểm thành viên, nhận ưu đãi riêng",
            "Đánh giá sản phẩm và xem đánh giá từ người dùng khác",
            "Lưu sản phẩm yêu thích, nhận thông báo khi có khuyến mãi",
        ]),
        ("Nếu quên mật khẩu, khách hàng có thể khôi phục theo các cách:", [
            "Nhấn <b>Quên mật khẩu</b> tại trang đăng nhập, nhập email để nhận liên kết đặt lại",
            "Khôi phục qua số điện thoại đã đăng ký bằng mã OTP",
            "Liên hệ CSKH cung cấp thông tin xác minh để hỗ trợ khôi phục",
        ]),
        "TechStore cam kết bảo mật thông tin khách hàng theo Luật An ninh mạng Việt Nam và tiêu chuẩn "
        "PCI DSS đối với dữ liệu thanh toán. Không chia sẻ thông tin cho bên thứ ba khi chưa có sự đồng ý.",
    ]),

    *section("11. Thông tin liên hệ", [
        ("Khách hàng có thể liên hệ TechStore qua nhiều kênh:", [
            "Tổng đài CSKH: 1900 1234 (8:00 đến 22:00 hằng ngày, gồm cả lễ tết)",
            "Email: cskh@techstore.vn - phản hồi trong 24 giờ làm việc",
            "Live chat: techstore.vn - hoạt động 24/7 với chatbot, 8:00 đến 22:00 với nhân viên",
            "Facebook: facebook.com/techstore.vn",
            "Zalo OA: TechStore Việt Nam",
        ]),
        ("Văn phòng và showroom:", [
            "Trụ sở Hà Nội: 123 Nguyễn Trãi, Thanh Xuân, Hà Nội",
            "Chi nhánh TP.HCM: 456 Nguyễn Văn Cừ, Quận 5, TP.HCM",
            "Chi nhánh Đà Nẵng: 789 Lê Duẩn, Hải Châu, Đà Nẵng",
        ]),
        "Giờ làm việc showroom: 9:00 đến 21:30 các ngày trong tuần, kể cả thứ 7 và Chủ nhật.",
    ]),
]


def build():
    out_path = Path(__file__).parent.parent / "data" / "cskh-tech-store.pdf"
    out_path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(out_path),
        pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title="Cẩm nang CSKH TechStore",
        author="TechStore",
    )
    doc.build(page1 + page2 + page3 + page4)
    print(f"Generated: {out_path}")
    print(f"Size: {out_path.stat().st_size:,} bytes")


if __name__ == "__main__":
    build()
