/**
 * TrustMeBro — Client-Side Bilingual Localization (VI / EN)
 * Seamlessly integrates across all application pages with shared localStorage state.
 */
(function() {
  'use strict';

  if (typeof window === 'undefined' || typeof document === 'undefined') return;

  const STORAGE_KEY = 'trustmebro-lang';
  const origTextMap = new WeakMap();
  const origAttrMap = new WeakMap();

  const PAGE_TITLES = {
    'landing': { vi: 'TrustMeBro — Mô phỏng Blockchain Giáo dục', en: 'TrustMeBro — Educational Blockchain Simulation' },
    'modes': { vi: 'Chọn chế độ — TrustMeBro', en: 'Choose Mode — TrustMeBro' },
    'theory': { vi: 'Lý thuyết — TrustMeBro', en: 'Theory Foundations — TrustMeBro' },
    'quiz': { vi: 'Trắc nghiệm — TrustMeBro', en: 'Quiz & Assessment — TrustMeBro' },
    'labs': { vi: 'Phòng thí nghiệm — TrustMeBro', en: 'Laboratories — TrustMeBro' },
    'journey': { vi: 'TrustMeBro — Mô phỏng Blockchain Giáo dục', en: 'TrustMeBro — Guided Journey' },
    'explorer': { vi: 'Block Explorer — TrustMeBro', en: 'Block Explorer — TrustMeBro' },
    'attacks': { vi: 'Tấn công & Phòng vệ — TrustMeBro', en: 'Attacks & Defenses — TrustMeBro' }
  };

  const DICTIONARY = {
    // Top Floating Pill Navbar (Option 1)
    "Trang chủ": "Home",
    "Lý thuyết": "Theory",
    "Chọn chế độ": "Modes",
    "Phòng lab": "Labs",
    "Trắc nghiệm": "Quiz",
    "Mở menu": "Open menu",
    "Đóng menu": "Close menu",
    "Chế độ sáng": "Light mode",
    "Chế độ tối": "Dark mode",
    "Switch to English": "Switch to English",
    "Chuyển sang tiếng Việt": "Chuyển sang tiếng Việt",

    // Modes Page (ui/modes.html)
    "TRUSTMEBRO / CHỌN CHẾ ĐỘ": "TRUSTMEBRO / CHOOSE MODE",
    "Bạn muốn bắt đầu theo cách nào?": "How would you like to start?",
    "Nắm vững lý thuyết nền tảng, đi từng bước với hành trình có hướng dẫn, tự thử các phép tính trong phòng thí nghiệm, hoặc kiểm tra kiến thức với bài trắc nghiệm.": "Master foundational theory, follow the guided journey, experiment in laboratories, or test knowledge with the interactive quiz.",
    "00 / NỀN TẢNG": "00 / FOUNDATIONS",
    "Hiểu bản chất Bitcoin, sổ cái phân tán, mật mã học và Proof of Work qua bài đọc dẫn dắt trực quan có video 3Blue1Brown.": "Understand Bitcoin, distributed ledgers, cryptography, and Proof of Work through visual reading with 3Blue1Brown video.",
    "Đọc bài dẫn nhập": "Read introduction",
    "Bài đọc 7 chương · Mục lục cuộn · 7 cầu nối thực hành": "7-chapter reading · Scrollable TOC · 7 practical lab bridges",
    "01 / TỪNG BƯỚC": "01 / STEP-BY-STEP",
    "Có hướng dẫn": "Guided Journey",
    "Từ chọn ví đến xác minh. Tự phát hành hồ sơ mẫu, tạo block và quan sát các bước kiểm tra.": "From wallet selection to verification. Issue sample credentials, forge blocks, and observe validation checks.",
    "Bắt đầu hành trình": "Start journey",
    "Ví → Hồ sơ → Mempool → PoW / PoS → Đồng bộ → Xác minh": "Wallet → Credential → Mempool → PoW / PoS → Sync → Verify",
    "02 / TỰ KHÁM PHÁ": "02 / EXPERIMENTS",
    "Phòng thí nghiệm": "Laboratories",
    "Tự nhập dữ liệu và lặp lại các thí nghiệm độc lập. Mỗi lab giữ ví, giao dịch, mạng và reset riêng; không có mạng sandbox dùng chung.": "Enter custom data and run isolated experiments. Each lab manages its own wallet, transactions, network, and reset state.",
    "Mở phòng thí nghiệm": "Open laboratories",
    "11 thí nghiệm độc lập thuộc 4 nhóm chủ đề.": "11 independent experiments across 4 topic groups.",
    "03 / ĐÁNH GIÁ": "03 / ASSESSMENT",
    "Thử thách và củng cố kiến thức về mật mã, Merkle tree, đồng thuận PoW/PoS và tấn công qua bộ câu hỏi tương tác.": "Challenge and reinforce concepts in cryptography, Merkle trees, PoW/PoS consensus, and network attacks with interactive questions.",
    "Làm bài trắc nghiệm": "Take quiz",
    "Bộ câu hỏi trắc nghiệm · Chấm điểm tức thì · Giải thích chi tiết": "Question bank · Instant scoring · Detailed explanations",
    "TRUSTMEBRO / PHÒNG THÍ NGHIỆM": "TRUSTMEBRO / LABORATORIES",
    "Một thay đổi nhỏ. Tự xem kết quả thật.": "A small change. Observe real results.",
    "Mỗi lab có dữ liệu và nút đặt lại riêng. Explorer chỉ đọc hành trình có hướng dẫn.": "Each lab has isolated data and reset. Explorer only reads the guided journey.",
    "Lộ trình 4 nhóm:": "4-group roadmap:",
    "Mật mã & Bằng chứng": "Cryptography & Proofs",
    "Kiểm tra toàn vẹn & người ký": "Integrity & signer verification",
    "01.1 · Mã băm": "01.1 · Hash function",
    "SHA-256": "SHA-256",
    "So sánh hai văn bản, toàn bộ hash và số bit thực sự thay đổi.": "Compare two inputs, full hash values, and exact bit differences.",
    "Thử phép băm": "Try hashing",
    "01.2 · Mã hóa bất đối xứng": "01.2 · Asymmetric Encryption",
    "RSA · Mã hóa": "RSA · Encryption",
    "Tạo cặp khóa RSA, mã hóa văn bản với OAEP padding và kiểm tra tính ngẫu nhiên cipher.": "Generate RSA key pair, encrypt plaintext with OAEP padding, and inspect ciphertext randomness.",
    "Thử mã hóa OAEP": "Try OAEP encryption",
    "01.3 · Chữ ký RSA": "01.3 · RSA Signature",
    "RSA · Chữ ký": "RSA · Signature",
    "Ký thông điệp với private key và PSS padding, xác minh bằng public key độc lập.": "Sign messages with private key and PSS padding, verify with independent public key.",
    "Thử ký và xác minh PSS": "Try PSS signing & verification",
    "01.4 · Xác thực ví": "01.4 · Wallet Authentication",
    "Chữ ký số": "Digital Signature",
    "Tạo khóa tạm, ký và sửa thông điệp để tự kiểm tra chữ ký ECDSA.": "Generate temporary keys, sign, and modify messages to inspect ECDSA verification.",
    "Thử ký và xác minh": "Try signing & verification",
    "01.5 · Bằng chứng dữ liệu": "01.5 · Data Proof",
    "Cây Merkle": "Merkle Tree",
    "Sửa một lá, xem nhánh và root thay đổi; kiểm tra bằng chứng một lá thuộc cây.": "Edit a leaf, observe branch and root changes; verify single-leaf inclusion proofs.",
    "Thử cây Merkle": "Try Merkle tree",
    "Giao dịch & Khối": "Transactions & Blocks",
    "Kiểm tra & ghi nhận dữ liệu": "Validation & data recording",
    "02.1 · Liên kết dữ liệu": "02.1 · Data Linking",
    "Khối & Chuỗi khối": "Blocks & Blockchain",
    "Tự nhập văn bản, thêm các khối nối từ genesis, mở header và thử sửa ngay trên thẻ khối.": "Enter custom text, append blocks from genesis, inspect headers, and test block tampering.",
    "Thử khối và chuỗi khối": "Try blocks & blockchain",
    "02.2 · Sắp xếp giao dịch": "02.2 · Transaction Ordering",
    "Hàng đợi & Phí": "Mempool & Fees",
    "Nộp giao dịch vào hàng đợi, quan sát phí ưu tiên và cách thợ đào chọn đưa vào block.": "Submit transactions to mempool, observe priority fees, and how miners select them for blocks.",
    "Thử hàng đợi mempool": "Try mempool queue",
    "Mạng & Đồng thuận": "Network & Consensus",
    "Đồng thuận & Bền vững": "Consensus & Sustainability",
    "03.1 · Đua tính toán": "03.1 · Computational Race",
    "Proof of Work": "Proof of Work",
    "Thay đổi độ khó, bấm đào và đo thời gian tìm nonce thỏa mãn số số 0 đầu hash.": "Adjust difficulty, mine, and measure time to find a nonce satisfying leading zeros.",
    "Thử đào PoW": "Try PoW mining",
    "03.2 · Trọng số cổ phần": "03.2 · Stake Weight",
    "Proof of Stake": "Proof of Stake",
    "Đặt cược token, quan sát xác suất chọn validator và ký tạo block mà không cần tốn điện.": "Stake tokens, observe validator selection probability, and sign blocks without energy waste.",
    "Thử chọn validator PoS": "Try PoS validator selection",
    "03.3 · Bất đồng thuận": "03.3 · Consensus Disagreement",
    "Rẽ nhánh & Tái tổ chức": "Forks & Reorganization",
    "Mô phỏng hai nhánh cạnh tranh cùng độ cao và quan sát quy tắc chuỗi dài nhất giải quyết fork.": "Simulate competing branches at the same height and watch the longest chain rule resolve the fork.",
    "Thử giải quyết rẽ nhánh": "Try fork resolution",
    "Tấn công & Giới hạn": "Attacks & Limitations",
    "Đồng bộ & Phòng thủ": "Sync & Defense",
    "04.1 · Đồng bộ phân tán": "04.1 · Distributed Sync",
    "Mạng 3 Node": "3-Node Network",
    "Quan sát lan truyền khối giữa 3 node, ngắt kết nối một node rồi kết nối lại để xem tự bắt kịp chuỗi.": "Observe block propagation across 3 nodes, disconnect one node, then reconnect to watch catch-up.",
    "Thử đồng bộ mạng": "Try network synchronization",
    "04.2 · Giới hạn an ninh": "04.2 · Security Limits",
    "Tấn công & Phòng thủ": "Attacks & Defenses",
    "Thử nghiệm sửa dữ liệu sau ký, giả danh người gửi và nộp lại giao dịch để xem lớp nào từ chối.": "Test post-signing tampering, impersonation, and replay attacks to see which layer rejects them.",
    "Thử các kịch bản tấn công": "Try attack scenarios",

    // Explorer Page (ui/explorer.html)
    "BLOCK EXPLORER / CHỈ ĐỌC": "BLOCK EXPLORER / READ-ONLY",
    "Xem block và giao dịch thật.": "Inspect real blocks and transactions.",
    "Xem blockchain của phiên mô phỏng có hướng dẫn.": "Inspect the blockchain of the guided simulation session.",
    "Explorer chỉ đọc dữ liệu; không tạo block hay đồng bộ node. Các lab dùng mạng riêng, không xuất hiện trong explorer này.": "Explorer only reads data; it does not forge blocks or sync nodes. Labs use separate networks and do not appear here.",
    "Bản blockchain cục bộ của": "Local blockchain ledger of",
    "Làm mới": "Refresh",
    "Đang tải…": "Loading…",
    "Chưa có block chứa giao dịch.": "No blocks containing transactions yet.",
    "Node được chọn mới có genesis. Tạo hồ sơ và block trong hành trình, rồi quay lại explorer; nếu node này đang ở phía sau, hãy kiểm tra mạng ở bước 5.": "The selected node only has genesis. Issue a credential and mine a block in the guided journey, then return to explorer.",
    "Tạo hồ sơ đầu tiên →": "Create first credential →",
    "Genesis — block khởi tạo": "Genesis — initial block",
    "Block mới nhất trước": "Latest blocks first",
    "Chi tiết block": "Block details",
    "Chọn một block để xem header và giao dịch.": "Select a block to inspect its header and transactions.",
    "Mô phỏng học tập: ba node trao đổi qua hàng đợi trong một server. Snapshot là dữ liệu tại lúc đọc; trang không tự polling. Hash hiển thị không phải chứng nhận chuỗi hợp lệ.": "Educational simulation: three nodes exchange via queues in one server. Snapshot reflects read-time data; no auto-polling.",

    // Attacks Page (ui/attacks.html)
    "08 · Tấn công & Phòng vệ": "08 · Attacks & Defenses",
    "Tấn công & Phòng vệ": "Attacks & Defenses",
    "Thử ba tình huống cố định và đọc lớp kiểm tra thực sự từ chối giao dịch. Không thao tác trên mạng có hướng dẫn hay lab khác.": "Test three fixed attack scenarios and identify which validation layer rejects the transaction. Does not alter guided journey.",
    "1. Mục tiêu học": "1. Learning Objectives",
    "Phân biệt nội dung bị đổi, chữ ký hợp lệ, quyền phát hành và giao dịch trùng. Giải thích lớp kiểm tra nào từ chối từng lượt dựa trên kết quả backend.": "Distinguish between modified content, valid signatures, issuance permissions, and duplicate transactions. Identify which validation layer rejected each attempt.",
    "2. Kiến thức nền": "2. Background Knowledge",
    "Hash đối chiếu nội dung với TxID đã ghi; chữ ký kiểm tra nội dung bằng khóa công khai. Quyền phát hành còn cần danh sách khóa được phép. Giao dịch đã nhận có thể bị từ chối khi nộp lại, dù chữ ký vẫn hợp lệ.": "Hashes verify content against recorded TxID; signatures verify content with public keys. Issuance authorization requires approved keys.",
    "Chữ ký hợp lệ không chứng minh nội dung đúng sự thật hoặc danh tính ngoài đời của người ký.": "A valid digital signature does not prove the factual truth of content or the real-world identity of the signer.",
    "3. Dự đoán — tùy chọn": "3. Prediction — Optional",
    "Bạn nghĩ lớp nào sẽ từ chối? Chữ ký có được kiểm tra không?": "Which layer do you predict will reject? Will the signature be verified?",
    "Ghi chú chỉ ở trang này, không gửi backend và không chấm tự động. Đối chiếu sau khi chạy.": "Notes stay in browser only; not sent to backend or graded automatically.",
    "4. Thực hành — chọn thí nghiệm": "4. Practice — Select Scenario",
    "Kịch bản": "Scenario",
    "Sửa nội dung sau khi ký": "Modify content after signing (Tamper)",
    "Giả danh đơn vị phát hành": "Impersonate unauthorized issuer",
    "Nộp lại giao dịch đã gửi": "Replay already-submitted transaction",
    "Tiêu đề thay thế trong giao dịch mẫu": "Replacement title in sample transaction",
    "Không trống và khác “Chứng chỉ mẫu lab”. Chỉ trường này được sửa.": "Must not be blank or equal to default. Only this field is editable.",
    "Chạy thử": "Run Test",
    "Đặt lại": "Reset",
    "Chọn kịch bản rồi bấm Chạy thử để tạo dữ liệu nền hợp lệ.": "Select a scenario and click Run Test to generate baseline data.",
    "5. Kết quả & nguyên nhân": "5. Results & Root Causes",
    "Chạy thử để đọc kết quả thực; hãy đối chiếu dự đoán với lý do từ chối và từng lớp kiểm tra.": "Run test to inspect actual results; compare prediction against rejection reasons.",
    "Nền hợp lệ và dữ liệu tấn công": "Baseline valid data and attack payload",
    "Chi tiết kỹ thuật — đầy đủ hash, khóa công khai và kết quả backend": "Technical details — complete hashes, public keys, and backend response",
    "6. Chiều sâu & giới hạn": "6. Depth & Limitations",
    "Cô lập, reset & cleanup": "Isolation, reset & cleanup",
    "Lý thuyết — chưa mô phỏng": "Theory — not simulated",
    "Mô phỏng học tập: các node chạy trong một server và giao tiếp qua hàng đợi. Không phải hệ thống đồng thuận production hay công cụ tấn công mạng thật.": "Educational simulation: nodes run in one server via queues. Not a production consensus system or real attack tool.",

    // Quiz Page (ui/quiz.html)
    "Tự thực hành": "Self-Practice",
    "Đi sâu và giới hạn mô phỏng học tập": "In-depth insights & learning simulation limits",
    "Mục tiêu kiểm tra": "Assessment Objectives",
    "Đánh giá sự hiểu biết toàn diện về bản chất sổ cái phân tán, hàm băm SHA-256, chữ ký số ECDSA/RSA, cấu trúc cây Merkle, cơ chế đồng thuận PoW/PoS, rẽ nhánh mạng và các khái niệm nâng cao của Blockchain.": "Comprehensively assess understanding of distributed ledgers, SHA-256, ECDSA/RSA signatures, Merkle trees, PoW/PoS consensus, and blockchain forks.",
    "Ngân hàng 400 câu hỏi": "400-Question Bank",
    "Gồm 400 câu hỏi trắc nghiệm chia theo 13 chủ đề môn học và 3 mức độ (Dễ, Vừa, Khó). Bài test tổng hợp chọn ngẫu nhiên 40 câu chia đều tỷ lệ theo các chủ đề trong 60 phút, yêu cầu đạt từ 70%.": "Contains 400 multiple-choice questions across 13 course topics and 3 difficulty tiers (Easy, Medium, Hard). Comprehensive exam samples 40 questions in 60 minutes.",
    "Ghi nhận tiến độ": "Progress Tracking",
    "Tiến độ làm bài và kết quả được lưu cục bộ trong bộ nhớ trình duyệt (localStorage). Điểm số chỉ nhằm mục đích tự ôn luyện học tập, không dùng để cấp chứng chỉ pháp lý ngoài đời thực.": "Quiz progress and scores are stored locally in localStorage. For educational self-assessment only.",
    "Xem lại kết quả & bài làm": "Review Results & Answers",
    "Sau khi hoàn thành lượt làm bài, bạn có thể xem thống kê tỷ lệ đúng theo từng chủ đề, tỷ lệ theo mức độ khó và xem lại chi tiết đáp án đúng của các câu làm sai hoặc chưa làm.": "Upon exam completion, view topic breakdown accuracy, difficulty distribution, and full explanations for incorrect questions.",
    "Bắt đầu làm bài": "Start Quiz",
    "Nộp bài": "Submit",
    "Làm lại": "Retake",
    "Tất cả chủ đề": "All Topics",
    "Dễ": "Easy",
    "Vừa": "Medium",
    "Khó": "Hard",
    "Đúng": "Correct",
    "Sai": "Incorrect",
    "Chưa trả lời": "Unanswered",
    "Thời gian còn lại:": "Time remaining:",
    "Giải thích chi tiết": "Detailed Explanation",
    "Bài kiểm tra tổng hợp": "Comprehensive Exam",
    "Luyện tập tự do": "Practice Mode",

    // Theory Page (ui/theory.html)
    "LÝ THUYẾT NỀN TẢNG": "FOUNDATIONAL THEORY",
    "Bản chất Bitcoin, Blockchain & Mật mã học": "Foundations of Bitcoin, Blockchain & Cryptography",
    "Mục lục bài đọc": "Table of Contents",
    "Chương 1: Sổ cái phân tán & Bài toán niềm tin": "Chapter 1: Distributed Ledgers & The Trust Problem",
    "Chương 2: Mật mã học — Hàm băm SHA-256 & Chữ ký số ECDSA": "Chapter 2: Cryptography — SHA-256 Hash & ECDSA Digital Signatures",
    "Chương 3: Cây Merkle — Xác thực dữ liệu hiệu quả": "Chapter 3: Merkle Tree — Efficient Data Verification",
    "Chương 4: Proof of Work — Đào khối & Cơ chế đồng thuận": "Chapter 4: Proof of Work — Block Mining & Consensus",
    "Chương 5: Proof of Stake — Lựa chọn thay thế tiết kiệm năng lượng": "Chapter 5: Proof of Stake — Energy-Efficient Alternative",
    "Chương 6: Mạng ngang hàng P2P & Xử lý rẽ nhánh": "Chapter 6: P2P Network & Fork Resolution",
    "Chương 7: Giới hạn bảo mật & Các cuộc tấn công thường gặp": "Chapter 7: Security Limits & Common Attacks",
    "Thực hành Lab SHA-256": "Practice SHA-256 Lab",
    "Thực hành Lab Chữ ký số": "Practice Digital Signature Lab",
    "Thực hành Lab Cây Merkle": "Practice Merkle Tree Lab",
    "Thực hành Lab Khối & PoW": "Practice Blocks & PoW Lab",
    "Thực hành Lab Rẽ nhánh": "Practice Fork Lab",
    "Thực hành Lab Mạng P2P": "Practice P2P Network Lab",
    "Thực hành Lab Tấn công": "Practice Attack Lab",
    "Làm bài trắc nghiệm củng cố kiến thức": "Take Quiz to reinforce knowledge",

    // Guided Journey Page (ui/trustmebro.html)
    "Từ hồ sơ đến bằng chứng": "From Credential to Proof",
    "Đi từng bước để hiểu một hồ sơ được ký, ghi vào blockchain và kiểm tra tính toàn vẹn như thế nào.": "Follow each step to understand how credentials are signed, committed to blockchain, and verified.",
    "Mô phỏng học tập · Ví ký bằng ECDSA": "Educational Simulation · ECDSA Key Signing",
    "Các tab cùng trình duyệt dùng chung phiên mô phỏng.": "Tabs in the same browser share the simulation session.",
    "Thông tin phiên": "Session Info",
    "Trình duyệt này có phiên mô phỏng riêng. Đặt lại chỉ xóa dữ liệu phiên này. Máy chủ khởi động lại hoặc phiên hết hạn có thể xóa dữ liệu; đây không phải mạng nhiều máy độc lập.": "This browser maintains an isolated session. Reset only clears this session's state.",
    "Mục tiêu:": "Goal:",
    "Kết quả:": "Observed:",
    "Tiếp theo:": "Next:",
    "BẠN ĐANG CHUẨN BỊ": "YOU ARE PREPARING",
    "Đơn vị phát hành hồ sơ": "Credential Issuer",
    "Bắt đầu từ người phát hành.": "Start from the issuer.",
    "Một ví đại diện cho đơn vị phát hành hồ sơ trong hành trình này.": "A wallet represents the issuing entity in this guided journey.",
    "Ví phát hành — ký hồ sơ": "Issuer wallet — credential signing",
    "Chưa chọn ví.": "No wallet selected.",
    "Đến bước hiện tại": "Skip to current step",
    "Bước 1: Ví phát hành": "Step 1: Issuer Wallet",
    "Bước 2: Ký hồ sơ": "Step 2: Sign Credential",
    "Bước 3: Mempool": "Step 3: Mempool",
    "Bước 4: Đào / Đúc block": "Step 4: Mine / Forge Block",
    "Bước 5: Mạng P2P": "Step 5: P2P Network",
    "Bước 6: Xác minh": "Step 6: Verification",
    "Tiếp tục": "Continue",
    "Quay lại": "Back",
    "Đặt lại phiên mô phỏng": "Reset Simulation Session",

    // Labs Page (ui/labs.html)
    "Chọn lab": "Select Lab",
    "Văn bản gốc": "Original text",
    "Văn bản so sánh": "Comparison text",
    "Số bit khác biệt:": "Differing bits:",
    "Tạo cặp khóa": "Generate Key Pair",
    "Ký thông điệp": "Sign Message",
    "Xác minh chữ ký": "Verify Signature",
    "Thêm khối": "Add Block",
    "Đào khối": "Mine Block",
    "Đặt lại lab": "Reset Lab",
    "Khôi phục mặc định": "Restore Defaults"
  };

  function getCurrentPage() {
    const p = window.location.pathname.toLowerCase();
    if (p.includes('modes')) return 'modes';
    if (p.includes('theory')) return 'theory';
    if (p.includes('quiz')) return 'quiz';
    if (p.includes('labs')) return 'labs';
    if (p.includes('trustmebro')) return 'journey';
    if (p.includes('explorer')) return 'explorer';
    if (p.includes('attacks')) return 'attacks';
    return 'landing';
  }

  function getLang() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'en' || saved === 'vi') return saved;
    } catch (e) {}
    return 'vi';
  }

  function translateNode(node, lang) {
    if (!node || node.nodeType !== 3) return;
    const raw = node.nodeValue;
    const trimmed = raw.trim();
    if (!trimmed) return;

    if (lang === 'en') {
      if (origTextMap.has(node)) return;
      if (Object.prototype.hasOwnProperty.call(DICTIONARY, trimmed)) {
        origTextMap.set(node, raw);
        node.nodeValue = raw.replace(trimmed, DICTIONARY[trimmed]);
      }
    } else {
      if (origTextMap.has(node)) {
        node.nodeValue = origTextMap.get(node);
        origTextMap.delete(node);
      }
    }
  }

  function translateAttributes(el, lang) {
    if (!el || el.nodeType !== 1) return;
    const attrs = ['placeholder', 'title', 'aria-label'];
    attrs.forEach(attr => {
      const val = el.getAttribute(attr);
      if (!val) return;
      const trimmed = val.trim();
      const mapKey = el;
      if (lang === 'en') {
        if (!origAttrMap.has(mapKey)) origAttrMap.set(mapKey, {});
        const saved = origAttrMap.get(mapKey);
        if (!saved[attr] && Object.prototype.hasOwnProperty.call(DICTIONARY, trimmed)) {
          saved[attr] = val;
          el.setAttribute(attr, DICTIONARY[trimmed]);
        }
      } else {
        if (origAttrMap.has(mapKey)) {
          const saved = origAttrMap.get(mapKey);
          if (saved[attr]) {
            el.setAttribute(attr, saved[attr]);
            delete saved[attr];
          }
        }
      }
    });
  }

  function walk(root, lang) {
    if (!root || typeof document.createTreeWalker !== 'function') return;

    const walker = document.createTreeWalker(
      root,
      NodeFilter.SHOW_TEXT,
      {
        acceptNode: function(n) {
          const parent = n.parentNode && n.parentNode.nodeName;
          if (parent === 'SCRIPT' || parent === 'STYLE' || parent === 'NOSCRIPT') {
            return NodeFilter.FILTER_REJECT;
          }
          return NodeFilter.FILTER_ACCEPT;
        }
      }
    );

    const textNodes = [];
    let cur;
    while ((cur = walker.nextNode())) {
      textNodes.push(cur);
    }
    textNodes.forEach(n => translateNode(n, lang));

    // Attributes on common elements
    const interactiveElements = root.querySelectorAll('button, input, textarea, a, select');
    interactiveElements.forEach(el => translateAttributes(el, lang));
  }

  function updateChrome(lang) {
    document.documentElement.lang = lang;
    const page = getCurrentPage();
    if (PAGE_TITLES[page] && PAGE_TITLES[page][lang]) {
      document.title = PAGE_TITLES[page][lang];
    }

    const langToggle = document.getElementById('lang-toggle');
    if (langToggle) {
      const isEn = lang === 'en';
      langToggle.textContent = isEn ? 'VI' : 'EN';
      const label = isEn ? 'Chuyển sang tiếng Việt' : 'Switch to English';
      langToggle.setAttribute('aria-label', label);
      langToggle.title = label;
    }

    const menuBtn = document.getElementById('menu-btn');
    if (menuBtn) {
      menuBtn.setAttribute('aria-label', lang === 'en' ? 'Toggle menu' : 'Mở menu');
    }
  }

  function applyLanguage(lang) {
    updateChrome(lang);
    walk(document.body, lang);
  }

  function setLanguage(lang) {
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch (e) {}
    applyLanguage(lang);
  }

  function init() {
    const currentLang = getLang();

    // Toggle button handler
    const langToggle = document.getElementById('lang-toggle');
    if (langToggle && !langToggle._hasI18nListener) {
      langToggle._hasI18nListener = true;
      langToggle.addEventListener('click', function(e) {
        e.preventDefault();
        const next = getLang() === 'vi' ? 'en' : 'vi';
        setLanguage(next);
      });
    }

    // Cross-tab sync
    window.addEventListener('storage', function(e) {
      if (e.key === STORAGE_KEY && (e.newValue === 'en' || e.newValue === 'vi')) {
        applyLanguage(e.newValue);
      }
    });

    // Observer for dynamically injected content
    if (window.MutationObserver) {
      let debounceTimer = null;
      const observer = new MutationObserver(function(mutations) {
        if (getLang() !== 'en') return;
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(function() {
          walk(document.body, 'en');
        }, 60);
      });
      observer.observe(document.body, { childList: true, subtree: true });
    }

    // Initial pass
    applyLanguage(currentLang);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }

  // Export minimal global for testing or programmatic triggering if needed
  window.__trustmebro_i18n = {
    getLang: getLang,
    setLanguage: setLanguage,
    applyLanguage: applyLanguage
  };
})();
