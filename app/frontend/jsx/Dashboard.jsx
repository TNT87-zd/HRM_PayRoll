import React, { useState } from 'react';

const Dashboard = () => {
  const [activeTab, setActiveTab] = useState('overview');

  return (
    <div className="flex min-h-screen bg-[#FDFBF7] font-sans text-gray-800">
      {/* SIDEBAR TỐI MÀU BÊN TRÁI */}
      <aside className="w-64 bg-[#1E1611] text-gray-300 flex flex-col justify-between p-4 shrink-0">
        <div>
          {/* Logo & Header Sidebar */}
          <div className="flex items-center gap-3 px-2 py-3 border-b border-gray-800 mb-4">
            <div className="w-10 h-10 bg-[#D9962B] rounded-xl flex items-center justify-center text-white text-xl font-bold shadow-md">
              ☕
            </div>
            <div>
              <h1 className="text-white font-bold text-sm tracking-wide">Cà Phê 5TN</h1>
              <p className="text-[11px] text-gray-400">HỆ THỐNG QUẢN TRỊ & BẢNG LƯƠNG</p>
              <span className="text-[9px] bg-gray-800 text-amber-400 px-1.5 py-0.5 rounded mt-1 inline-block font-mono">v4.2 PRO</span>
            </div>
          </div>

          {/* Navigation Menu */}
          <nav className="space-y-6 text-xs">
            <div>
              <div className="px-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2">Vận hành chi nhánh</div>
              <ul className="space-y-1">
                <li>
                  <a href="/admin.html" className="flex items-center gap-3 px-3 py-2.5 rounded-lg bg-[#33261D] text-white font-semibold">
                    <span className="text-base">📊</span> Tổng quan
                  </a>
                </li>
                <li>
                  <a href="/kiosk.html" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#2A1F17] hover:text-white transition">
                    <span className="text-base">📸</span> Điểm danh Kiosk
                  </a>
                </li>
              </ul>
            </div>

            <div>
              <div className="px-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2">Chấm công & Tài chính</div>
              <ul className="space-y-1">
                <li>
                  <a href="/enroll.html" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#2A1F17] hover:text-white transition">
                    <span className="text-base">👤</span> Đăng ký Khuôn mặt
                  </a>
                </li>
                <li>
                  <a href="/portal.html#schedule" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#2A1F17] hover:text-white transition">
                    <span className="text-base">📅</span> Lịch làm việc & Ca
                  </a>
                </li>
                <li>
                  <a href="/portal.html#attendance" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#2A1F17] hover:text-white transition">
                    <span className="text-base">⏱</span> Bảng chấm công
                  </a>
                </li>
                <li>
                  <a href="/portal.html#leave" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#2A1F17] hover:text-white transition justify-between">
                    <div className="flex items-center gap-3">
                      <span className="text-base">📝</span> Phê duyệt
                    </div>
                    <span className="bg-amber-600 text-white text-[10px] font-bold px-1.5 py-0.2 rounded-full">12</span>
                  </a>
                </li>
                <li>
                  <a href="/portal.html#salary" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#2A1F17] hover:text-white transition">
                    <span className="text-base">💵</span> Tính lương
                  </a>
                </li>
              </ul>
            </div>

            <div>
              <div className="px-3 text-[10px] font-bold text-gray-500 uppercase tracking-wider mb-2">Hệ thống</div>
              <ul className="space-y-1">
                <li>
                  <a href="#" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#2A1F17] hover:text-white transition">
                    <span className="text-base">👥</span> Nhân sự
                  </a>
                </li>
                <li>
                  <a href="#" className="flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-[#2A1F17] hover:text-white transition">
                    <span className="text-base">📋</span> Nhật ký hệ thống
                  </a>
                </li>
              </ul>
            </div>
          </nav>
        </div>

        {/* Footer Sidebar Button */}
        <div className="pt-4 border-t border-gray-800">
          <div className="bg-[#2A1F17] p-3 rounded-xl border border-gray-800 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping"></span>
              <span className="text-[11px] font-medium text-gray-300">Đồng bộ POS/Kiosk</span>
            </div>
            <span className="text-[10px] text-gray-500 font-mono">Live</span>
          </div>
        </div>
      </aside>

      {/* NỘI DUNG CHÍNH (MAIN CONTENT) */}
      <main className="flex-1 flex flex-col min-w-0 overflow-y-auto">
        {/* HEADER TOP BAR */}
        <header className="bg-white border-b border-gray-200 px-8 py-3 flex items-center justify-between sticky top-0 z-10">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 bg-gray-100 px-3 py-1.5 rounded-lg border border-gray-200 text-xs">
              <span className="text-gray-400">Chi nhánh:</span>
              <select className="bg-transparent font-bold text-gray-700 outline-none cursor-pointer">
                <option value="CN01">Chi nhánh Hải Châu</option>
                <option value="CN02">Chi nhánh Sơn Trà</option>
                <option value="CN03">Chi nhánh Hòa Khánh</option>
              </select>
            </div>
            <div className="relative">
              <input
                type="text"
                placeholder="Tìm kiếm barista, mã nhân viên, ca làm..."
                className="w-72 bg-gray-50 border border-gray-200 rounded-lg pl-8 pr-3 py-1.5 text-xs focus:bg-white focus:outline-none focus:ring-1 focus:ring-amber-500"
              />
              <span className="absolute left-2.5 top-2 text-xs text-gray-400">🔍</span>
            </div>
          </div>

          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 bg-emerald-50 border border-emerald-200 text-emerald-700 text-xs px-3 py-1.5 rounded-full font-medium">
              <span className="w-2 h-2 rounded-full bg-emerald-500"></span>
              Kiosk Sync Live (18/18)
            </span>
            <div className="h-4 w-px bg-gray-200"></div>
            <div className="flex items-center gap-3 text-xs">
              <div className="w-8 h-8 rounded-full bg-amber-600 text-white font-bold flex items-center justify-center text-xs">
                TH
              </div>
              <div>
                <div className="font-bold text-gray-800 leading-tight">Trương Nhật Trường</div>
                <div className="text-[10px] text-gray-400">HR Ops Director</div>
              </div>
            </div>
          </div>
        </header>

        {/* DASHBOARD BODY */}
        <div className="p-8 space-y-6">
          {/* TITLE & ACTION BUTTONS */}
          <div className="flex flex-wrap items-center justify-between gap-4">
            <div>
              <div className="flex items-center gap-3">
                <h1 className="text-2xl font-extrabold text-[#2C1D11]">Xin chào, Nhật Trường 👋</h1>
                <span className="bg-emerald-100 text-emerald-800 text-xs font-bold px-2.5 py-0.5 rounded-full">
                  HỆ THỐNG TRỰC TUYẾN
                </span>
              </div>
              <p className="text-xs text-gray-500 mt-1 flex items-center gap-4">
                <span>🟢 <b>142/148</b> Quản lý đang trong ca</span>
                <span>🔴 <b>4</b> Đúng giờ</span>
                <span>🟡 <b>2</b> Xin đổi ca chờ duyệt</span>
                <span className="text-gray-400">Kỳ lương: 01/10 - 31/10/2024</span>
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button className="bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-xs font-bold px-3.5 py-2 rounded-lg shadow-sm flex items-center gap-1">
                <span>⏱</span> + Xếp ca khẩn cấp
              </button>
              <button className="bg-white border border-gray-300 hover:bg-gray-50 text-gray-700 text-xs font-bold px-3.5 py-2 rounded-lg shadow-sm">
                📝 Kỳ tính lương T10
              </button>
              <button className="bg-[#2C1D11] hover:bg-[#1E1611] text-white text-xs font-bold px-4 py-2 rounded-lg shadow-sm flex items-center gap-1">
                <span>📥</span> Xuất báo cáo ca
              </button>
            </div>
          </div>

          {/* 4 METRIC CARDS */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Card 1 */}
            <div className="bg-white p-5 rounded-2xl border border-gray-200/80 shadow-sm relative">
              <div className="flex justify-between items-start">
                <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wide">TỶ LỆ CÓ MẶT HÔM NAY</span>
                <span className="p-2 bg-emerald-50 text-emerald-600 rounded-xl text-xs">👥</span>
              </div>
              <div className="text-3xl font-extrabold text-gray-900 mt-2">96.8%</div>
              <div className="text-xs text-emerald-600 font-semibold mt-2 flex items-center gap-1">
                <span>📈 +2.4% vs tuần trước</span>
                <span className="text-gray-400 font-normal">142/148 Nhân sự</span>
              </div>
            </div>

            {/* Card 2 */}
            <div className="bg-white p-5 rounded-2xl border border-gray-200/80 shadow-sm relative">
              <div className="flex justify-between items-start">
                <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wide">CHI PHÍ LƯƠNG T10 (ƯỚC TÍNH)</span>
                <span className="p-2 bg-amber-50 text-amber-600 rounded-xl text-xs">💵</span>
              </div>
              <div className="text-3xl font-extrabold text-gray-900 mt-2">đ485.2M</div>
              <div className="text-xs text-gray-500 font-medium mt-2 flex items-center gap-1">
                <span className="text-amber-600 font-semibold">Đạt 94% ngân sách</span>
                <span className="text-gray-400">Hạn mức 515M</span>
              </div>
            </div>

            {/* Card 3 */}
            <div className="bg-white p-5 rounded-2xl border border-gray-200/80 shadow-sm relative">
              <div className="flex justify-between items-start">
                <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wide">GIỜ LÀM THÊM (OT) TÍCH LŨY</span>
                <span className="p-2 bg-rose-50 text-rose-600 rounded-xl text-xs">⏰</span>
              </div>
              <div className="text-3xl font-extrabold text-gray-900 mt-2">328h</div>
              <div className="text-xs text-rose-500 font-semibold mt-2 flex items-center gap-1">
                <span>⚠️ 3 Chi nhánh vượt trần</span>
                <span className="text-gray-400 font-normal">+38h so với chỉ tiêu</span>
              </div>
            </div>

            {/* Card 4 */}
            <div className="bg-white p-5 rounded-2xl border border-gray-200/80 shadow-sm relative">
              <div className="flex justify-between items-start">
                <span className="text-[11px] font-bold text-gray-400 uppercase tracking-wide">FACE ID KIOSK AI MATCHING</span>
                <span className="p-2 bg-indigo-50 text-indigo-600 rounded-xl text-xs">🎯</span>
              </div>
              <div className="text-3xl font-extrabold text-gray-900 mt-2">99.4%</div>
              <div className="text-xs text-emerald-600 font-semibold mt-2 flex items-center gap-1">
                <span>⚡ 0.38s/lượt chấm</span>
                <span className="text-gray-400 font-normal">18/18 Kiosks online</span>
              </div>
            </div>
          </div>

          {/* MAIN SECTION GRID (LEFT: GRAPH + BRANCHES, RIGHT: SIDE PANELS) */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            
            {/* CỘT TRÁI (2 COLS) */}
            <div className="lg:col-span-2 space-y-6">
              
              {/* BIỂU ĐỒ MẬT ĐỘ CHẤM CÔNG */}
              <div className="bg-white p-6 rounded-2xl border border-gray-200/80 shadow-sm">
                <div className="flex justify-between items-start mb-4">
                  <div>
                    <h2 className="text-base font-bold text-gray-900">Mật độ Chấm công Face ID Theo Giờ</h2>
                    <p className="text-xs text-gray-400">Phân bố ca sáng (Peak 06:30 - 07:15) và ca trưa chuyển giao (14:00 - 15:00)</p>
                  </div>
                  <div className="flex gap-1 bg-gray-100 p-1 rounded-lg text-[11px] font-medium">
                    <button className="px-2.5 py-1 bg-white rounded-md shadow-xs text-gray-800 font-bold">Hôm nay</button>
                    <button className="px-2.5 py-1 text-gray-500 hover:text-gray-800">Hôm qua</button>
                    <button className="px-2.5 py-1 text-gray-500 hover:text-gray-800">Trung bình tuần</button>
                  </div>
                </div>

                {/* Giả lập đường biểu đồ đồ họa SVG */}
                <div className="h-52 relative mt-6">
                  <svg className="w-full h-full overflow-visible" viewBox="0 0 500 150" preserveAspectRatio="none">
                    <path
                      d="M 0 130 Q 60 20 120 110 T 250 30 T 380 120 T 500 130"
                      fill="none"
                      stroke="#8B5E34"
                      strokeWidth="3"
                    />
                    <path
                      d="M 0 130 Q 60 20 120 110 T 250 30 T 380 120 T 500 130 L 500 150 L 0 150 Z"
                      fill="url(#grad)"
                      opacity="0.15"
                    />
                    <defs>
                      <linearGradient id="grad" x1="0%" y1="0%" x2="0%" y2="100%">
                        <stop offset="0%" stopColor="#8B5E34" />
                        <stop offset="100%" stopColor="#ffffff" />
                      </linearGradient>
                    </defs>
                  </svg>
                  {/* Tooltip điểm Đỉnh ca sáng */}
                  <div className="absolute top-4 left-[22%] bg-gray-900 text-white text-[10px] px-2 py-1 rounded shadow-md pointer-events-none">
                    68 lượt (07:00 Ca Sáng)
                  </div>
                  {/* Tooltip điểm Đỉnh ca chiều */}
                  <div className="absolute top-6 left-[48%] bg-gray-900 text-white text-[10px] px-2 py-1 rounded shadow-md pointer-events-none">
                    74 lượt (14:30 Đổi ca)
                  </div>
                </div>

                <div className="flex justify-between text-[11px] text-gray-400 mt-2 font-mono border-t pt-3">
                  <span>06:00 (Mở cửa)</span>
                  <span>07:30</span>
                  <span>09:30</span>
                  <span>12:00</span>
                  <span>14:30 (Đổi ca)</span>
                  <span>17:00</span>
                  <span>20:00</span>
                  <span>22:30 (Đóng cửa)</span>
                </div>

                <div className="flex justify-between items-center mt-4 pt-3 border-t border-gray-100 text-xs">
                  <div className="flex gap-4">
                    <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-[#8B5E34]"></span> Tổng lượt Check-in: <b>286 lượt</b></span>
                    <span className="flex items-center gap-1.5"><span className="w-2.5 h-2.5 rounded-full bg-emerald-500"></span> Đúng giờ: <b>97.2%</b></span>
                  </div>
                  <span className="text-gray-400 text-[11px]">Cập nhật mỗi 30s từ Cloud Edge</span>
                </div>
              </div>

              {/* TÌNH HÌNH NHÂN SỰ TRỰC TIẾP TẠI CỬA HÀNG */}
              <div className="bg-white p-6 rounded-2xl border border-gray-200/80 shadow-sm">
                <div className="flex justify-between items-center mb-4">
                  <div>
                    <h2 className="text-base font-bold text-gray-900">Tình Hình Nhân Sự Trực Tiếp Tại Cửa Hàng</h2>
                    <p className="text-xs text-gray-400">Tỷ lệ cơ cấu: Barista pha chế / Thu ngân POS / Phục vụ bàn</p>
                  </div>
                  <span className="bg-gray-100 text-gray-600 text-xs font-semibold px-2.5 py-1 rounded-lg">4 Chi nhánh trọng điểm</span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {/* Branch 1 */}
                  <div className="p-4 rounded-xl border border-gray-100 bg-gray-50/50 space-y-3">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <span className="p-2 bg-amber-100 text-amber-800 rounded-lg text-xs">🏢</span>
                        <div>
                          <div className="font-bold text-sm text-gray-800">Quận Hải Châu</div>
                          <div className="text-[10px] text-gray-400">Flagship • Giờ cao điểm</div>
                        </div>
                      </div>
                      <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5 rounded">Đủ 100% quân số</span>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs font-semibold mb-1">
                        <span>Hiện diện: 16/16 nhân sự</span>
                        <span className="text-emerald-600">100%</span>
                      </div>
                      <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                        <div className="bg-emerald-500 h-full w-full"></div>
                      </div>
                    </div>
                    <div className="flex gap-2 text-[11px] text-gray-500 pt-1 border-t border-gray-200/60">
                      <span>• 8 Barista</span>
                      <span>• 4 Thu ngân</span>
                      <span>• 4 Phục vụ</span>
                    </div>
                  </div>

                  {/* Branch 2 */}
                  <div className="p-4 rounded-xl border border-gray-100 bg-gray-50/50 space-y-3">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <span className="p-2 bg-rose-100 text-rose-800 rounded-lg text-xs">🏛</span>
                        <div>
                          <div className="font-bold text-sm text-gray-800">Quận Sơn Trà</div>
                          <div className="text-[10px] text-gray-400">Chi nhánh di sản • Ca 1</div>
                        </div>
                      </div>
                      <span className="bg-rose-100 text-rose-800 text-[10px] font-bold px-2 py-0.5 rounded">Thiếu 1 Barista</span>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs font-semibold mb-1">
                        <span>Hiện diện: 11/12 nhân sự</span>
                        <span className="text-amber-600">91.6%</span>
                      </div>
                      <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                        <div className="bg-amber-500 h-full w-[91.6%]"></div>
                      </div>
                    </div>
                    <div className="flex gap-2 text-[11px] text-gray-500 pt-1 border-t border-gray-200/60">
                      <span className="text-rose-600 font-semibold">• 5/6 Barista</span>
                      <span>• 3 Thu ngân</span>
                      <span>• 3 Phục vụ</span>
                    </div>
                  </div>

                  {/* Branch 3 */}
                  <div className="p-4 rounded-xl border border-gray-100 bg-gray-50/50 space-y-3">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <span className="p-2 bg-indigo-100 text-indigo-800 rounded-lg text-xs">🌿</span>
                        <div>
                          <div className="font-bold text-sm text-gray-800">Quận Hòa Khánh</div>
                          <div className="text-[10px] text-gray-400">Không gian mở ngoài trời</div>
                        </div>
                      </div>
                      <span className="bg-emerald-100 text-emerald-800 text-[10px] font-bold px-2 py-0.5 rounded">Đủ 14/14</span>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs font-semibold mb-1">
                        <span>Hiện diện: 14/14 nhân sự</span>
                        <span className="text-emerald-600">100%</span>
                      </div>
                      <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                        <div className="bg-emerald-500 h-full w-full"></div>
                      </div>
                    </div>
                    <div className="flex gap-2 text-[11px] text-gray-500 pt-1 border-t border-gray-200/60">
                      <span>• 6 Barista</span>
                      <span>• 4 Thu ngân</span>
                      <span>• 4 Phục vụ</span>
                    </div>
                  </div>

                  {/* Branch 4 */}
                  <div className="p-4 rounded-xl border border-gray-100 bg-gray-50/50 space-y-3">
                    <div className="flex justify-between items-center">
                      <div className="flex items-center gap-2">
                        <span className="p-2 bg-orange-100 text-orange-800 rounded-lg text-xs">☕</span>
                        <div>
                          <div className="font-bold text-sm text-gray-800">Quận Thanh Khê</div>
                          <div className="text-[10px] text-gray-400">Phố ẩm thực • Đang đổi ca</div>
                        </div>
                      </div>
                      <span className="bg-amber-100 text-amber-800 text-[10px] font-bold px-2 py-0.5 rounded">1 Đang vào trễ</span>
                    </div>
                    <div>
                      <div className="flex justify-between text-xs font-semibold mb-1">
                        <span>Hiện diện: 12/13 nhân sự</span>
                        <span className="text-amber-600">92.3%</span>
                      </div>
                      <div className="w-full bg-gray-200 h-2 rounded-full overflow-hidden">
                        <div className="bg-amber-500 h-full w-[92.3%]"></div>
                      </div>
                    </div>
                    <div className="flex gap-2 text-[11px] text-gray-500 pt-1 border-t border-gray-200/60">
                      <span>• 6 Barista</span>
                      <span>• 3 Thu ngân</span>
                      <span className="text-amber-600 font-semibold">• 3/4 Phục vụ (Trễ 10p)</span>
                    </div>
                  </div>
                </div>
              </div>

            </div>

            {/* CỘT PHẢI (1 COL) */}
            <div className="space-y-6">
              
              {/* CẦN PHÊ DUYỆT GẤP (4 ĐƠN) */}
              <div className="bg-[#FFFDF9] p-5 rounded-2xl border border-amber-200/80 shadow-sm relative">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-sm font-extrabold text-amber-900 flex items-center gap-2">
                    <span>⚡</span> Cần Phê Duyệt Gấp <span className="bg-amber-500 text-white text-[10px] px-2 py-0.2 rounded-full">4 Đơn</span>
                  </h2>
                </div>

                <div className="space-y-3">
                  {/* Request Item 1 */}
                  <div className="bg-white p-3.5 rounded-xl border border-amber-100 shadow-xs space-y-2">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-bold text-xs text-gray-800">Nguyễn Hữu Tâm</div>
                        <div className="text-[10px] text-gray-400">Ca chiều (14:30) ➔ Nhờ Lê Ngọc Mai thay ca • Lý do: Sốt nhẹ</div>
                      </div>
                      <span className="bg-amber-100 text-amber-800 text-[9px] font-bold px-1.5 py-0.5 rounded">Đổi ca làm</span>
                    </div>
                    <div className="flex gap-2 pt-1">
                      <button className="flex-1 py-1 text-xs border border-gray-200 text-gray-600 font-semibold rounded hover:bg-gray-50">Từ chối</button>
                      <button className="flex-1 py-1 text-xs bg-emerald-600 text-white font-bold rounded hover:bg-emerald-700">Duyệt ngay</button>
                    </div>
                  </div>

                  {/* Request Item 2 */}
                  <div className="bg-white p-3.5 rounded-xl border border-amber-100 shadow-xs space-y-2">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-bold text-xs text-gray-800">Võ Thị Kim Oanh</div>
                        <div className="text-[10px] text-gray-400">Ca tối qua 22:30 CN Hải Châu • Xin giải trình rời quầy hỗ trợ kiểm kê kho</div>
                      </div>
                      <span className="bg-rose-100 text-rose-800 text-[9px] font-bold px-1.5 py-0.5 rounded">Quên Check-out</span>
                    </div>
                    <div className="flex gap-2 pt-1">
                      <button className="flex-1 py-1 text-xs border border-gray-200 text-gray-600 font-semibold rounded hover:bg-gray-50">Xem camera</button>
                      <button className="flex-1 py-1 text-xs bg-emerald-600 text-white font-bold rounded hover:bg-emerald-700">Xác nhận công</button>
                    </div>
                  </div>

                  {/* Request Item 3 */}
                  <div className="bg-white p-3.5 rounded-xl border border-amber-100 shadow-xs space-y-2">
                    <div className="flex justify-between items-start">
                      <div>
                        <div className="font-bold text-xs text-gray-800">Đặng Hoàng Bách</div>
                        <div className="text-[10px] text-gray-400">Hỗ trợ giờ cao điểm Workshop Cà phê tại CN Sơn Trà</div>
                      </div>
                      <span className="bg-amber-100 text-amber-800 text-[9px] font-bold px-1.5 py-0.5 rounded">Đăng ký OT (+3h)</span>
                    </div>
                    <div className="flex gap-2 pt-1">
                      <button className="flex-1 py-1 text-xs border border-gray-200 text-gray-600 font-semibold rounded hover:bg-gray-50">Chi tiết</button>
                      <button className="flex-1 py-1 text-xs bg-gray-900 text-white font-bold rounded hover:bg-gray-800">Chấp thuận</button>
                    </div>
                  </div>
                </div>

                <div className="text-center mt-3 pt-2 border-t border-amber-100">
                  <a href="/portal.html#leave" className="text-xs text-amber-800 font-bold hover:underline inline-flex items-center gap-1">
                    Xem toàn bộ danh sách phê duyệt (12 đơn) ➔
                  </a>
                </div>
              </div>

              {/* NHẬT KÝ FACE ID KIOSK LIVE */}
              <div className="bg-white p-5 rounded-2xl border border-gray-200/80 shadow-sm">
                <div className="flex justify-between items-center mb-4">
                  <h2 className="text-sm font-bold text-gray-900 flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span> Nhật Kỳ Face ID Kiosk Live
                  </h2>
                  <span className="text-[10px] text-gray-400 font-mono">Auto-Sync</span>
                </div>

                <div className="space-y-3">
                  <div className="flex items-center justify-between p-2 rounded-xl hover:bg-gray-50 border border-gray-100">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-amber-100 text-amber-800 font-bold flex items-center justify-center text-xs">LN</div>
                      <div>
                        <div className="font-bold text-xs text-gray-800">Mai Văn Chung</div>
                        <div className="text-[10px] text-gray-400">Barista Trưởng • Thanh Khê</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-xs font-bold text-gray-800">06:28:14</div>
                      <div className="text-[10px] text-emerald-600 font-semibold">Khớp 99.8%</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-2 rounded-xl hover:bg-gray-50 border border-gray-100">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-blue-100 text-blue-800 font-bold flex items-center justify-center text-xs">NM</div>
                      <div>
                        <div className="font-bold text-xs text-gray-800">Nguyễn Mai Phương</div>
                        <div className="text-[10px] text-gray-400">Thu ngân POS • Thanh Khê</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-xs font-bold text-gray-800">06:31:02</div>
                      <div className="text-[10px] text-emerald-600 font-semibold">Khớp 99.4%</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-2 rounded-xl hover:bg-gray-50 border border-gray-100">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-purple-100 text-purple-800 font-bold flex items-center justify-center text-xs">QT</div>
                      <div>
                        <div className="font-bold text-xs text-gray-800">Đỗ Quốc Thắng</div>
                        <div className="text-[10px] text-gray-400">Barista Part-time • Sơn Trà</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-xs font-bold text-gray-800">06:45:22</div>
                      <div className="text-[10px] text-emerald-600 font-semibold">Khớp 98.9%</div>
                    </div>
                  </div>

                  <div className="flex items-center justify-between p-2 rounded-xl bg-rose-50/60 border border-rose-100">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-full bg-rose-100 text-rose-800 font-bold flex items-center justify-center text-xs">TM</div>
                      <div>
                        <div className="font-bold text-xs text-gray-800">Vũ Thị Trúc My</div>
                        <div className="text-[10px] text-gray-400">Phục vụ • Thanh Khê</div>
                      </div>
                    </div>
                    <div className="text-right">
                      <div className="font-mono text-xs font-bold text-rose-600">07:12:05</div>
                      <div className="text-[10px] text-rose-600 font-bold">Trễ 12 phút</div>
                    </div>
                  </div>
                </div>

                <div className="mt-4 pt-3 border-t border-gray-100">
                  <button className="w-full py-2 bg-gray-50 hover:bg-gray-100 text-gray-700 text-xs font-bold rounded-lg border border-gray-200 flex items-center justify-center gap-1">
                    <span>📺</span> Xem Trực Tiếp Kiosk Kèm HUD
                  </button>
                </div>
              </div>

            </div>

          </div>
        </div>
      </main>
    </div>
  );
};

export default Dashboard;