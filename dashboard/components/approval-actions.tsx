import { Check, X } from "lucide-react";

import { approveApproval, denyApproval } from "@/app/actions";
import type { ApprovalRequest } from "@/lib/types";

export function ApprovalActions({ approval }: { approval: ApprovalRequest }) {
  return (
    <div className="stack">
      <form action={approveApproval} className="form-row">
        <input name="approval_id" type="hidden" value={approval.id} />
        <input className="input mono" name="user_id" placeholder="approver user id" required />
        <input className="input" name="note" placeholder="approval note" />
        <button className="button" type="submit">
          <Check aria-hidden="true" size={15} />
          Approve
        </button>
        <button className="button danger" formAction={denyApproval} type="submit">
          <X aria-hidden="true" size={15} />
          Deny
        </button>
      </form>
    </div>
  );
}
