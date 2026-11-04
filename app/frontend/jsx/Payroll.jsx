import React from 'react';

const Payroll = () => {
  return (
    <div className="bg-white p-6 rounded-xl shadow-sm border border-gray-200">
      <div className="flex justify-between items-center mb-6 border-b pb-4">
        <div>
          <h2 className="font-bold text-lg text-[#3D2517]">Phiếu lương điện tử - Cafe 5TN</h2>
          <p className="text-xs text-gray-500">Đã đối soát giờ công từ FaceID</p>
        </div>
        <button className="bg-green-600 text-white px-4 py-2 rounded text-sm font-bold shadow-sm">Xuất Excel / Chốt Lương</button>
      </div>
      
      <table className="w-full text-sm text-left">
        <thead className="bg-gray-50 text-gray-500 text-xs uppercase border-b">
          <tr><th className="p-3">Mã NV</th><th className="p-3">Họ tên</th><th className="p-3 text-right">Giờ công</th><th className="p-3 text-right">Lương cơ bản</th><th className="p-3 text-right text-[#3D2517]">Thực lĩnh (NET)</th></tr>
        </thead>
        <tbody>
          <tr className="border-b hover:bg-gray-50">
            <td className="p-3 font-mono">NV0001</td><td className="p-3 font-bold">Lê Hoàng Nam</td><td className="p-3 text-right">176h</td>
            <td className="p-3 text-right">6.160.000đ</td><td className="p-3 text-right font-bold text-lg text-green-700">7.120.000đ</td>
          </tr>
          <tr className="border-b hover:bg-gray-50">
            <td className="p-3 font-mono">NV0002</td><td className="p-3 font-bold">Đặng Mai Lan</td><td className="p-3 text-right">160h</td>
            <td className="p-3 text-right">5.600.000đ</td><td className="p-3 text-right font-bold text-lg text-green-700">6.350.000đ</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
};

export default Payroll;