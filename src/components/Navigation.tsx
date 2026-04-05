import { Settings, FileCheck } from 'lucide-react';

interface NavigationProps {
  currentPage: 'setup' | 'dashboard';
  onNavigate: (page: 'setup' | 'dashboard') => void;
}

export default function Navigation({ currentPage, onNavigate }: NavigationProps) {
  return (
    <nav className="bg-white shadow-sm border-b border-gray-200 sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center">
            <h1 className="text-xl font-bold text-gray-900">Label & EDI Validator</h1>
          </div>

          <div className="flex space-x-4">
            <button
              onClick={() => onNavigate('setup')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                currentPage === 'setup'
                  ? 'bg-[#4a4337] text-white'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              <Settings className="w-5 h-5" />
              Carrier Setup
            </button>

            <button
              onClick={() => onNavigate('dashboard')}
              className={`flex items-center gap-2 px-4 py-2 rounded-lg font-medium transition-colors ${
                currentPage === 'dashboard'
                  ? 'bg-[#4a4337] text-white'
                  : 'text-gray-700 hover:bg-gray-100'
              }`}
            >
              <FileCheck className="w-5 h-5" />
              Validation
            </button>
          </div>
        </div>
      </div>
    </nav>
  );
}