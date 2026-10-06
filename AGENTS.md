# Quy tắc sửa code

Áp dụng [Karpathy guidelines của multica-ai](https://github.com/multica-ai/andrej-karpathy-skills):

- Nêu giả định và phạm vi trước khi sửa; nói rõ điều chưa kiểm chứng.
- Chọn cách sửa đơn giản nhất đáp ứng yêu cầu, không thêm tính năng dự phòng.
- Chỉ sửa phần liên quan, giữ phong cách hiện có, không refactor ngoài phạm vi.
- Với lỗi logic/bảo mật: viết test tái hiện, xác nhận thất bại trước khi sửa,
  rồi chạy `python -m pytest -q` để kiểm tra hồi quy.
- Với thay đổi Streamlit: kiểm tra trang và thao tác liên quan bằng AppTest
  hoặc chạy ứng dụng thực tế; phân biệt rõ hai loại kiểm tra.

Quy ước của dự án:

- SHA-256 vẫn là thuật toán băm; JSON chỉ là cách mã hóa đầu vào nhất quán.
- Xác minh PoS cần registry đáng tin cậy; có chuỗi chữ ký chưa có nghĩa chữ ký hợp lệ.
- Benchmark phải phân biệt số liệu đo với giả định; không suy ra điện năng từ số lần băm.
- Đây là mô phỏng học tập. Không mô tả nó là hệ thống đồng thuận production.
