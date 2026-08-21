import api from "@/lib/api"
import type {
  SharedGroup,
  SharedGroupMember,
  SharedExpense,
  GroupDetail,
  MemberBalance,
  GroupCreate,
  MemberCreate,
  ExpenseCreate,
  GroupFundContribution,
  GroupFundContributionCreate,
  FundStatus,
} from "@/lib/types"

export const sharedService = {
  async listGroups(): Promise<SharedGroup[]> {
    try {
      const response = await api.get<SharedGroup[]>("/shared/groups")
      return response.data
    } catch (error) {
      throw error
    }
  },

  async createGroup(data: GroupCreate): Promise<SharedGroup> {
    try {
      const response = await api.post<SharedGroup>("/shared/groups", data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async getGroup(id: number): Promise<GroupDetail> {
    try {
      const response = await api.get<GroupDetail>(`/shared/groups/${id}`)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async addMember(
    groupId: number,
    data: MemberCreate
  ): Promise<SharedGroupMember> {
    try {
      const response = await api.post<SharedGroupMember>(
        `/shared/groups/${groupId}/members`,
        data
      )
      return response.data
    } catch (error) {
      throw error
    }
  },

  async addExpense(
    groupId: number,
    data: ExpenseCreate
  ): Promise<SharedExpense> {
    try {
      const response = await api.post<SharedExpense>(
        `/shared/groups/${groupId}/expenses`,
        data
      )
      return response.data
    } catch (error) {
      throw error
    }
  },

  async getBalances(groupId: number): Promise<MemberBalance[]> {
    try {
      const response = await api.get<MemberBalance[]>(
        `/shared/groups/${groupId}/balances`
      )
      return response.data
    } catch (error) {
      throw error
    }
  },

  async settleBetween(groupId: number, debtorId: number, creditorId: number): Promise<void> {
    try {
      await api.put(`/shared/groups/${groupId}/settle-between`, null, {
        params: { debtor_id: debtorId, creditor_id: creditorId },
      })
    } catch (error) {
      throw error
    }
  },

  async settleSelectedSplits(groupId: number, splitIds: number[], creditorMemberId: number): Promise<void> {
    try {
      await api.post(`/shared/groups/${groupId}/settle-splits`, {
        split_ids: splitIds,
        creditor_member_id: creditorMemberId,
      })
    } catch (error) {
      throw error
    }
  },

  async leaveGroup(groupId: number): Promise<void> {
    try {
      await api.delete(`/shared/groups/${groupId}/leave`)
    } catch (error) {
      throw error
    }
  },

  async contributeFund(groupId: number, data: GroupFundContributionCreate): Promise<GroupFundContribution> {
    try {
      const response = await api.post<GroupFundContribution>(`/shared/groups/${groupId}/fund/contribute`, data)
      return response.data
    } catch (error) {
      throw error
    }
  },

  async getFundStatus(groupId: number): Promise<FundStatus> {
    try {
      const response = await api.get<FundStatus>(`/shared/groups/${groupId}/fund`)
      return response.data
    } catch (error) {
      throw error
    }
  },
}
