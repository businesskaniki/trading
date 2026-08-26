import { FaExclamationTriangle, FaTimes } from "react-icons/fa";
import "../../css/confirmModal.css";

const ConfirmModal = ({ isOpen, title, message, confirmLabel = "Confirm", danger = false, loading = false, onConfirm, onClose }) => {
  if (!isOpen) return null;

  return (
    <div className="confirm-modal-overlay" onMouseDown={(event) => event.target === event.currentTarget && !loading && onClose()}>
      <div className="confirm-modal" role="dialog" aria-modal="true" aria-labelledby="confirm-modal-title">
        <button className="confirm-modal__close" type="button" onClick={onClose} disabled={loading} aria-label="Close"><FaTimes /></button>
        <div className={danger ? "confirm-modal__icon confirm-modal__icon--danger" : "confirm-modal__icon"}><FaExclamationTriangle /></div>
        <h2 id="confirm-modal-title">{title}</h2>
        <p>{message}</p>
        <div className="confirm-modal__actions">
          <button className="confirm-modal__cancel" type="button" onClick={onClose} disabled={loading}>Cancel</button>
          <button className={danger ? "confirm-modal__confirm confirm-modal__confirm--danger" : "confirm-modal__confirm"} type="button" onClick={onConfirm} disabled={loading}>{loading ? "Working..." : confirmLabel}</button>
        </div>
      </div>
    </div>
  );
};

export default ConfirmModal;
