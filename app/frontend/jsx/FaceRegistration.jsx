import React from 'react';

const FaceRegistration = () => {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-[#3D2517]">Thu thập Dữ liệu Khuôn mặt & Liveness</h1>
      
      <div className="flex gap-6">
        <div className="flex-1 bg-white p-5 rounded-xl shadow-sm border border-gray-200">
          <div className="flex justify-between items-center mb-4">
            <h2 className="font-bold text-[#3D2517]">Kiosk Biometric Capture Studio</h2>
            <span className="text-red-500 text-xs font-bold animate-pulse">● LIVE CAM 01</span>
          </div>
          
          <div className="bg-gray-900 h-[400px] rounded-xl relative overflow-hidden mb-6 flex justify-center border-4 border-gray-800">
            <video id="video" autoPlay playsInline muted className="h-full object-cover"></video>
            <div id="oval" className="absolute border-2 border-dashed border-white/50 w-56 h-72 rounded-[100px] top-8"></div>
          </div>
          
          <div className="flex gap-4 mt-6">
            <button id="startCapture" className="flex-1 bg-[#D9962B] text-white py-3 rounded-lg font-bold shadow-md hover:bg-[#b87c1f]">Bắt đầu quét</button>
            <button id="commitCapture" className="flex-1 bg-green-600 text-white py-3 rounded-lg font-bold shadow-md opacity-50" disabled>Lưu Model AI</button>
          </div>
        </div>

        <div className="w-96 bg-white p-5 rounded-xl shadow-sm border border-gray-200">
          <h3 className="font-bold text-[#3D2517] border-b pb-2 mb-4">Hồ sơ Barista</h3>
          <form id="profileForm" className="space-y-4">
            <div>
              <label className="text-xs font-bold text-gray-500">Mã Nhân Viên</label>
              <input type="text" id="employeeId" defaultValue="NV0001" className="w-full border rounded p-2 text-sm bg-gray-50" readOnly />
            </div>
            <div>
              <label className="text-xs font-bold text-gray-500">Họ và tên</label>
              <input type="text" id="fullName" placeholder="Nhập tên nhân viên..." className="w-full border border-gray-300 rounded p-2 text-sm" />
            </div>
            <div>
              <label className="text-xs font-bold text-gray-500">Chi nhánh</label>
              <select id="branchId" className="w-full border border-gray-300 rounded p-2 text-sm">
                <option value="CN01">Đồng Khởi</option>
              </select>
            </div>
          </form>
        </div>
      </div>
    </div>
  );
};

export default FaceRegistration;