import React from 'react';

const KioskAttendance = () => {
  return (
    <div className="h-full flex flex-col space-y-4">
      <div className="bg-white p-4 rounded-xl shadow-sm border border-gray-200 flex justify-between items-center mb-4">
        <div>
          <div className="text-xs text-gray-500 uppercase font-bold flex items-center gap-2">ĐIỂM DANH KIOSK <span className="bg-green-600 text-white px-2 py-0.5 rounded text-[10px]">Trực tuyến (Live)</span></div>
          <h2 className="text-xl font-bold text-[#3D2517] mt-1">Cafe 5TN - Chi nhánh Đồng Khởi</h2>
        </div>
        <div className="text-right">
          <div id="clock" className="text-2xl font-bold text-[#3D2517]">00:00:00</div>
          <div id="today" className="text-xs text-gray-500">Hôm nay</div>
        </div>
      </div>

      <div className="flex gap-4 mb-4">
        <button id="btnIn" className="flex-1 py-3 text-lg font-bold rounded-xl transition bg-green-600 text-white shadow-md">👋 Chấm công VÀO (Check-in)</button>
        <button id="btnOut" className="flex-1 py-3 text-lg font-bold rounded-xl transition bg-white border border-gray-300 text-gray-700 shadow-sm hover:bg-gray-50">🏃 Chấm công RA (Check-out)</button>
      </div>

      <div className="flex gap-6 h-full">
        {/* Camera Feed cho AI */}
        <div className="flex-1 bg-black rounded-xl relative overflow-hidden flex items-center justify-center shadow-lg border-4 border-gray-800 h-[600px]">
          <video id="cam" autoPlay muted playsInline className="absolute inset-0 w-full h-full object-contain"></video>
          <canvas id="overlay" className="absolute inset-0 w-full h-full"></canvas>
          <div className="absolute bottom-6 bg-black/60 text-white px-4 py-2 rounded-full text-sm z-10">Đang căn chỉnh khuôn mặt vào khung hình...</div>
        </div>
        
        {/* Log bên phải */}
        <div className="w-96 flex flex-col gap-4">
          <div id="card" className="bg-white p-6 rounded-xl shadow-sm border-2 border-green-500 bg-green-50">
            <p id="title" className="text-2xl font-bold text-green-700 mb-1">Đang chờ quét...</p>
            <p id="sub" className="text-gray-600 text-sm">Nhìn thẳng vào camera</p>
          </div>
          <div className="bg-white p-5 rounded-xl shadow-sm border border-gray-200 flex-1 overflow-y-auto">
            <h3 className="font-bold text-[#3D2517] border-b pb-2 mb-3">Nhật ký Điểm danh</h3>
            <ul id="history" className="space-y-3">
              {/* JS AI sẽ append log vào đây */}
            </ul>
          </div>
        </div>
      </div>
    </div>
  );
};

export default KioskAttendance;