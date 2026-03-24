#include <algorithm>
#include <array>
#include <chrono>
#include <cstdlib>
#include <functional>
#include <iostream>
#include <limits>
#include <optional>
#include <string>
#include <utility>
#include <vector>

class CostasSearcher {
  public:
    CostasSearcher(int order, double time_limit_seconds,
                   const std::vector<std::pair<int, int>>& fixed_assignments,
                   const std::vector<int>& focus_widths)
        : n_(order),
          assigned_(order, 0),
          row_used_(order + 1, false),
          row_to_column_(order + 1, -1),
          diff_used_(order, std::vector<char>(2 * order, false)),
          dyadic_shifts_(BuildDyadicShifts(order)),
          focus_width_weights_(order, 0),
          deadline_(std::chrono::steady_clock::now() +
                    std::chrono::milliseconds(static_cast<int>(time_limit_seconds * 1000.0))) {
        for (int row = 1; row <= n_; ++row) {
            if ((row & 1) == 0) {
                ++unused_even_count_;
            } else {
                ++unused_odd_count_;
            }
        }
        int weight = static_cast<int>(focus_widths.size());
        for (int width : focus_widths) {
            if (width > 0 && width < n_ && focus_width_weights_[width] == 0) {
                focus_width_weights_[width] = std::max(1, weight);
                --weight;
            }
        }
        ApplyFixedAssignments(fixed_assignments);
    }

    bool Search() {
        if (inconsistent_) {
            return false;
        }
        return SearchRecursive();
    }

    bool timed_out() const { return timed_out_; }

    long long nodes() const { return nodes_; }

    const std::vector<int>& solution() const { return assigned_; }

  private:
    const int n_;
    std::vector<int> assigned_;
    std::vector<char> row_used_;
    std::vector<int> row_to_column_;
    std::vector<std::vector<char>> diff_used_;
    std::vector<int> dyadic_shifts_;
    std::vector<int> focus_width_weights_;
    int assigned_count_ = 0;
    long long nodes_ = 0;
    int unused_odd_count_ = 0;
    int unused_even_count_ = 0;
    bool timed_out_ = false;
    bool inconsistent_ = false;
    std::chrono::steady_clock::time_point deadline_;

    static std::vector<int> BuildDyadicShifts(int order) {
        std::vector<int> shifts;
        for (int shift = 1; shift < order; shift <<= 1) {
            shifts.push_back(shift);
        }
        return shifts;
    }

    bool SearchRecursive() {
        if ((nodes_ & 0x3FF) == 0 &&
            std::chrono::steady_clock::now() >= deadline_) {
            timed_out_ = true;
            return false;
        }

        if (assigned_count_ == n_) {
            return true;
        }

        ++nodes_;

        std::vector<std::vector<int>> domains(n_);
        int column = ChooseColumn(domains);
        if (column < 0) {
            return false;
        }

        if (!HasPerfectMatching(domains)) {
            return false;
        }

        std::vector<int> candidates = domains[column];
        OrderCandidates(column, candidates, domains);
        for (int row : candidates) {
            std::vector<std::pair<int, int>> changes;
            Place(column, row, changes);
            if (StructuralFiltersConsistent() && DyadicFiltersConsistent() && SearchRecursive()) {
                return true;
            }
            Undo(column, row, changes);
            if (timed_out_) {
                return false;
            }
        }

        return false;
    }

    int ChooseColumn(std::vector<std::vector<int>>& domains) {
        int best_column = -1;
        std::size_t best_domain = std::numeric_limits<std::size_t>::max();
        int best_pressure = std::numeric_limits<int>::min();
        for (int column = 0; column < n_; ++column) {
            if (assigned_[column] != 0) {
                continue;
            }
            if (!CollectCandidates(column, domains[column])) {
                return -1;
            }
            std::size_t domain_size = domains[column].size();
            int pressure = ColumnPressureScore(column);
            if (domain_size < best_domain) {
                best_domain = domain_size;
                best_column = column;
                best_pressure = pressure;
            } else if (domain_size == best_domain &&
                       (pressure > best_pressure ||
                        (pressure == best_pressure && BetterColumn(column, best_column)))) {
                best_column = column;
                best_pressure = pressure;
            }
        }

        if (assigned_[0] == 0) {
            return 0;
        }
        if (assigned_[n_ - 1] == 0) {
            return n_ - 1;
        }
        return best_column;
    }

    bool BetterColumn(int candidate, int current) const {
        if (current < 0) {
            return true;
        }
        int candidate_priority = std::min(candidate, n_ - 1 - candidate);
        int current_priority = std::min(current, n_ - 1 - current);
        if (candidate_priority != current_priority) {
            return candidate_priority < current_priority;
        }
        return candidate < current;
    }

    bool CollectCandidates(int column, std::vector<int>& out) {
        out.clear();
        for (int row = 1; row <= n_; ++row) {
            if (Feasible(column, row)) {
                out.push_back(row);
            }
        }
        return !out.empty();
    }

    void OrderCandidates(int column, std::vector<int>& candidates,
                         const std::vector<std::vector<int>>& domains) {
        if (column == 0) {
            return;
        }

        std::stable_sort(
            candidates.begin(), candidates.end(),
            [this, column, &domains](int left, int right) {
                int left_score = CandidateImpact(column, left, domains);
                int right_score = CandidateImpact(column, right, domains);
                if (left_score != right_score) {
                    return left_score > right_score;
                }
                return left < right;
            });
    }

    int CandidateImpact(int column, int row, const std::vector<std::vector<int>>& domains) const {
        int score = 0;
        for (int other = 0; other < n_; ++other) {
            if (other == column || assigned_[other] != 0) {
                continue;
            }
            int remaining = 0;
            for (int other_row : domains[other]) {
                if (other_row == row) {
                    continue;
                }
                if (PairFeasible(column, row, other, other_row)) {
                    ++remaining;
                }
            }
            score += remaining;
        }
        return score;
    }

    int ColumnPressureScore(int column) const {
        int score = 0;
        for (int width = 1; width < n_; ++width) {
            const int weight = focus_width_weights_[width];
            if (weight == 0) {
                continue;
            }

            int local = 0;
            if (column - width >= 0) {
                local += (assigned_[column - width] != 0) ? 3 : 1;
            }
            if (column + width < n_) {
                local += (assigned_[column + width] != 0) ? 3 : 1;
            }
            score += weight * local;
        }
        return score;
    }

    bool Feasible(int column, int row) const {
        if (row_used_[row]) {
            return false;
        }

        if (!SymmetryConsistent(column, row)) {
            return false;
        }

        std::vector<std::pair<int, int>> local_diffs;
        for (int other = 0; other < n_; ++other) {
            if (assigned_[other] == 0) {
                continue;
            }

            int distance = 0;
            int delta = 0;
            if (other < column) {
                distance = column - other;
                delta = row - assigned_[other];
            } else {
                distance = other - column;
                delta = assigned_[other] - row;
            }

            int index = delta + (n_ - 1);
            if (diff_used_[distance][index]) {
                return false;
            }
            if (std::find(local_diffs.begin(), local_diffs.end(), std::make_pair(distance, index)) !=
                local_diffs.end()) {
                return false;
            }
            local_diffs.push_back(std::make_pair(distance, index));
        }

        return true;
    }

    bool PairFeasible(int left_column, int left_row, int right_column, int right_row) const {
        int distance = std::abs(right_column - left_column);
        int delta = 0;
        if (left_column < right_column) {
            delta = right_row - left_row;
        } else {
            delta = left_row - right_row;
        }
        int index = delta + (n_ - 1);
        return !diff_used_[distance][index];
    }

    bool SymmetryConsistent(int column, int row) const {
        if (column == 0) {
            if (row > (n_ + 1) / 2) {
                return false;
            }

            auto column_consistent = [row, this](int col_index) {
                int one_based = col_index + 1;
                return row <= one_based && one_based <= (n_ + 1 - row);
            };

            if (assigned_[n_ - 1] != 0) {
                int last = assigned_[n_ - 1];
                if (last < row || last > (n_ + 1 - row)) {
                    return false;
                }
            }
            if (row_to_column_[1] >= 0 && !column_consistent(row_to_column_[1])) {
                return false;
            }
            if (row_to_column_[n_] >= 0 && !column_consistent(row_to_column_[n_])) {
                return false;
            }
            return true;
        }
        if (assigned_[0] == 0) {
            return true;
        }

        int first = assigned_[0];
        if (column == n_ - 1) {
            if (row < first || row > (n_ + 1 - first)) {
                return false;
            }
        }

        auto column_consistent = [first, this](int col_index) {
            int one_based = col_index + 1;
            return first <= one_based && one_based <= (n_ + 1 - first);
        };

        if (row == 1 && !column_consistent(column)) {
            return false;
        }
        if (row == n_ && !column_consistent(column)) {
            return false;
        }

        if (row_to_column_[1] >= 0 && !column_consistent(row_to_column_[1])) {
            return false;
        }
        if (row_to_column_[n_] >= 0 && !column_consistent(row_to_column_[n_])) {
            return false;
        }
        if (assigned_[n_ - 1] != 0) {
            int last = assigned_[n_ - 1];
            if (last < first || last > (n_ + 1 - first)) {
                return false;
            }
        }

        return true;
    }

    bool CanonicalStateConsistent() const {
        if (assigned_[0] == 0) {
            return true;
        }

        int first = assigned_[0];
        if (first > (n_ + 1) / 2) {
            return false;
        }

        auto column_consistent = [first, this](int col_index) {
            int one_based = col_index + 1;
            return first <= one_based && one_based <= (n_ + 1 - first);
        };

        if (assigned_[n_ - 1] != 0) {
            int last = assigned_[n_ - 1];
            if (last < first || last > (n_ + 1 - first)) {
                return false;
            }
        }
        if (row_to_column_[1] >= 0 && !column_consistent(row_to_column_[1])) {
            return false;
        }
        if (row_to_column_[n_] >= 0 && !column_consistent(row_to_column_[n_])) {
            return false;
        }

        return true;
    }

    bool StructuralFiltersConsistent() const {
        return EvenQuadrantConstraintFeasible() && SmallMirrorPairFeasible();
    }

    bool EvenQuadrantConstraintFeasible() const {
        if ((n_ & 1) != 0 || n_ <= 6) {
            return true;
        }

        const int half = n_ / 2;
        int unused_top = 0;
        for (int row = 1; row <= half; ++row) {
            if (!row_used_[row]) {
                ++unused_top;
            }
        }
        const int unused_bottom = unused_even_count_ + unused_odd_count_ - unused_top;

        return HalfColumnBlockQuadrantsFeasible(0, half, half, unused_top, unused_bottom) &&
               HalfColumnBlockQuadrantsFeasible(half, n_, half, unused_top, unused_bottom);
    }

    bool HalfColumnBlockQuadrantsFeasible(int start_column, int end_column, int half,
                                          int unused_top, int unused_bottom) const {
        int assigned_top = 0;
        int assigned_bottom = 0;
        int unassigned = 0;

        for (int column = start_column; column < end_column; ++column) {
            const int row = assigned_[column];
            if (row == 0) {
                ++unassigned;
            } else if (row <= half) {
                ++assigned_top;
            } else {
                ++assigned_bottom;
            }
        }

        const int min_extra_top = std::max(0, unassigned - unused_bottom);
        const int max_extra_top = std::min(unassigned, unused_top);
        const int min_final_top = assigned_top + min_extra_top;
        const int max_final_top = assigned_top + max_extra_top;
        return !(max_final_top < 1 || min_final_top > half - 1);
    }

    bool DyadicFiltersConsistent() const {
        return HalfShiftParityFeasible() && DyadicBoundaryFiltersConsistent();
    }

    bool HalfShiftParityFeasible() const {
        if ((n_ & 1) != 0) {
            return true;
        }

        const int shift = n_ / 2;
        const int target_parity = shift & 1;
        std::vector<char> reachable((unused_odd_count_ + 1) * 2, false);
        std::vector<char> next((unused_odd_count_ + 1) * 2, false);
        reachable[0] = true;
        int slots_used = 0;

        for (int index = 0; index < shift; ++index) {
            std::fill(next.begin(), next.end(), false);
            const int left = assigned_[index];
            const int right = assigned_[index + shift];
            int slot_increment = 0;
            std::array<std::pair<int, int>, 3> transitions{};
            int transition_count = 0;

            if (left != 0 && right != 0) {
                transitions[transition_count++] = std::make_pair(0, (left ^ right) & 1);
            } else if (left != 0 || right != 0) {
                const int assigned_parity = ((left != 0) ? left : right) & 1;
                slot_increment = 1;
                transitions[transition_count++] = std::make_pair(0, assigned_parity);
                transitions[transition_count++] = std::make_pair(1, assigned_parity ^ 1);
            } else {
                slot_increment = 2;
                transitions[transition_count++] = std::make_pair(0, 0);
                transitions[transition_count++] = std::make_pair(1, 1);
                transitions[transition_count++] = std::make_pair(2, 0);
            }

            const int next_slots_used = slots_used + slot_increment;
            for (int odd_used = 0; odd_used <= unused_odd_count_; ++odd_used) {
                for (int parity = 0; parity < 2; ++parity) {
                    if (!reachable[odd_used * 2 + parity]) {
                        continue;
                    }
                    for (int transition = 0; transition < transition_count; ++transition) {
                        const int next_odd_used = odd_used + transitions[transition].first;
                        if (next_odd_used > unused_odd_count_) {
                            continue;
                        }
                        const int even_used = next_slots_used - next_odd_used;
                        if (even_used > unused_even_count_) {
                            continue;
                        }
                        next[next_odd_used * 2 + (parity ^ transitions[transition].second)] = true;
                    }
                }
            }

            slots_used = next_slots_used;
            reachable.swap(next);
        }

        return reachable[unused_odd_count_ * 2 + target_parity];
    }

    bool DyadicBoundaryFiltersConsistent() const {
        for (int shift : dyadic_shifts_) {
            int target_sum = 0;
            if (!BoundarySumIfExact(shift, target_sum)) {
                continue;
            }
            if (!ShiftDifferencePoolFeasible(shift, target_sum)) {
                return false;
            }
        }
        return true;
    }

    bool BoundarySumIfExact(int shift, int& target_sum) const {
        target_sum = 0;
        for (int column = 0; column < n_; ++column) {
            const int coefficient = ((column >= n_ - shift) ? 1 : 0) - ((column < shift) ? 1 : 0);
            if (coefficient == 0) {
                continue;
            }
            if (assigned_[column] == 0) {
                return false;
            }
            target_sum += coefficient * assigned_[column];
        }
        return true;
    }

    bool ShiftDifferencePoolFeasible(int shift, int target_sum) const {
        int completed_sum = 0;
        int completed_pairs = 0;
        for (int index = 0; index + shift < n_; ++index) {
            if (assigned_[index] == 0 || assigned_[index + shift] == 0) {
                continue;
            }
            completed_sum += assigned_[index + shift] - assigned_[index];
            ++completed_pairs;
        }

        const int remaining_pairs = (n_ - shift) - completed_pairs;
        const int remaining_target = target_sum - completed_sum;
        if (remaining_pairs == 0) {
            return remaining_target == 0;
        }

        std::vector<int> available_differences;
        available_differences.reserve(2 * n_);
        int odd_available = 0;
        int even_available = 0;
        for (int delta = -(n_ - 1); delta <= (n_ - 1); ++delta) {
            if (delta == 0) {
                continue;
            }
            const int index = delta + (n_ - 1);
            if (diff_used_[shift][index]) {
                continue;
            }
            available_differences.push_back(delta);
            if ((std::abs(delta) & 1) == 0) {
                ++even_available;
            } else {
                ++odd_available;
            }
        }

        if (remaining_pairs > static_cast<int>(available_differences.size())) {
            return false;
        }

        int min_sum = 0;
        int max_sum = 0;
        for (int index = 0; index < remaining_pairs; ++index) {
            min_sum += available_differences[index];
            max_sum += available_differences[available_differences.size() - 1 - index];
        }
        if (remaining_target < min_sum || remaining_target > max_sum) {
            return false;
        }

        if (!SubsetParityFeasible(remaining_pairs, odd_available, even_available, remaining_target)) {
            return false;
        }

        return SubsetResidueMod4Feasible(available_differences, remaining_pairs, remaining_target);
    }

    bool SubsetParityFeasible(int subset_size, int odd_available, int even_available,
                              int target_sum) const {
        const int target_parity = PositiveMod(target_sum, 2);
        const int min_odd = std::max(0, subset_size - even_available);
        const int max_odd = std::min(subset_size, odd_available);
        for (int odd_count = min_odd; odd_count <= max_odd; ++odd_count) {
            if ((odd_count & 1) == target_parity) {
                return true;
            }
        }
        return false;
    }

    bool SubsetResidueMod4Feasible(const std::vector<int>& available_differences,
                                   int subset_size, int target_sum) const {
        std::vector<std::array<char, 4>> reachable(subset_size + 1);
        reachable[0][0] = true;

        for (int delta : available_differences) {
            const int residue = PositiveMod(delta, 4);
            for (int used = subset_size - 1; used >= 0; --used) {
                for (int previous = 0; previous < 4; ++previous) {
                    if (!reachable[used][previous]) {
                        continue;
                    }
                    reachable[used + 1][(previous + residue) & 3] = true;
                }
            }
        }

        return reachable[subset_size][PositiveMod(target_sum, 4)];
    }

    static int PositiveMod(int value, int modulus) {
        const int remainder = value % modulus;
        return remainder >= 0 ? remainder : remainder + modulus;
    }

    bool SmallMirrorPairFeasible() const {
        if (n_ < 6 || assigned_count_ < n_ / 2) {
            return true;
        }

        for (int width = 1; width <= 2 && width < n_; ++width) {
            std::vector<int> fixed_differences;
            fixed_differences.reserve(n_ - width);
            for (int start = 0; start + width < n_; ++start) {
                if (assigned_[start] != 0 && assigned_[start + width] != 0) {
                    fixed_differences.push_back(assigned_[start + width] - assigned_[start]);
                }
            }
            for (int difference : fixed_differences) {
                if (difference > 0 &&
                    std::find(fixed_differences.begin(), fixed_differences.end(), -difference) !=
                        fixed_differences.end()) {
                    return true;
                }
            }

            for (int height = 1; height < n_; ++height) {
                int positive_windows = 0;
                int negative_windows = 0;
                int overlap_windows = 0;

                for (int start = 0; start + width < n_; ++start) {
                    const bool can_positive = WindowCanRealizeDifference(start, width, height);
                    const bool can_negative = WindowCanRealizeDifference(start, width, -height);
                    if (can_positive) {
                        ++positive_windows;
                    }
                    if (can_negative) {
                        ++negative_windows;
                    }
                    if (can_positive && can_negative) {
                        ++overlap_windows;
                    }
                }

                if (positive_windows > 0 && negative_windows > 0 &&
                    positive_windows + negative_windows - overlap_windows >= 2) {
                    return true;
                }
            }
        }

        return false;
    }

    bool WindowCanRealizeDifference(int start, int width, int difference) const {
        const int left_column = start;
        const int right_column = start + width;
        const int left_row = assigned_[left_column];
        const int right_row = assigned_[right_column];

        if (left_row != 0 && right_row != 0) {
            return right_row - left_row == difference;
        }

        const int diff_index = difference + (n_ - 1);
        if (diff_index < 0 || diff_index >= 2 * n_ - 1) {
            return false;
        }
        if (diff_used_[width][diff_index]) {
            return false;
        }

        if (left_row != 0) {
            const int candidate = left_row + difference;
            return candidate >= 1 && candidate <= n_ && !row_used_[candidate] &&
                   Feasible(right_column, candidate);
        }

        if (right_row != 0) {
            const int candidate = right_row - difference;
            return candidate >= 1 && candidate <= n_ && !row_used_[candidate] &&
                   Feasible(left_column, candidate);
        }

        for (int candidate_left = 1; candidate_left <= n_; ++candidate_left) {
            if (row_used_[candidate_left]) {
                continue;
            }
            const int candidate_right = candidate_left + difference;
            if (candidate_right < 1 || candidate_right > n_ || row_used_[candidate_right]) {
                continue;
            }
            if (candidate_left == candidate_right) {
                continue;
            }
            if (Feasible(left_column, candidate_left) && Feasible(right_column, candidate_right)) {
                return true;
            }
        }

        return false;
    }

    bool HasPerfectMatching(const std::vector<std::vector<int>>& domains) const {
        std::vector<int> columns;
        for (int column = 0; column < n_; ++column) {
            if (assigned_[column] == 0) {
                columns.push_back(column);
            }
        }

        std::sort(columns.begin(), columns.end(), [&domains](int left, int right) {
            return domains[left].size() < domains[right].size();
        });

        std::vector<int> matched_row(n_ + 1, -1);
        for (int column : columns) {
            std::vector<char> seen(n_ + 1, false);
            std::function<bool(int)> augment = [&](int current_column) -> bool {
                for (int row : domains[current_column]) {
                    if (seen[row]) {
                        continue;
                    }
                    seen[row] = true;
                    if (matched_row[row] < 0 || augment(matched_row[row])) {
                        matched_row[row] = current_column;
                        return true;
                    }
                }
                return false;
            };
            if (!augment(column)) {
                return false;
            }
        }
        return true;
    }

    void Place(int column, int row, std::vector<std::pair<int, int>>& changes) {
        assigned_[column] = row;
        row_used_[row] = true;
        row_to_column_[row] = column;
        if ((row & 1) == 0) {
            --unused_even_count_;
        } else {
            --unused_odd_count_;
        }
        ++assigned_count_;

        for (int other = 0; other < n_; ++other) {
            if (other == column || assigned_[other] == 0) {
                continue;
            }

            int distance = 0;
            int delta = 0;
            if (other < column) {
                distance = column - other;
                delta = row - assigned_[other];
            } else {
                distance = other - column;
                delta = assigned_[other] - row;
            }

            int index = delta + (n_ - 1);
            diff_used_[distance][index] = true;
            changes.push_back(std::make_pair(distance, index));
        }
    }

    void Undo(int column, int row, const std::vector<std::pair<int, int>>& changes) {
        for (const auto& change : changes) {
            diff_used_[change.first][change.second] = false;
        }
        --assigned_count_;
        if ((row & 1) == 0) {
            ++unused_even_count_;
        } else {
            ++unused_odd_count_;
        }
        row_to_column_[row] = -1;
        row_used_[row] = false;
        assigned_[column] = 0;
    }

    void ApplyFixedAssignments(const std::vector<std::pair<int, int>>& fixed_assignments) {
        std::vector<std::pair<int, int>> ordered = fixed_assignments;
        std::stable_sort(ordered.begin(), ordered.end(), [this](const auto& left, const auto& right) {
            if (left.first == 0 || right.first == 0) {
                return left.first == 0;
            }
            if (left.first == n_ - 1 || right.first == n_ - 1) {
                return left.first == n_ - 1;
            }
            return left.first < right.first;
        });

        for (const auto& assignment : ordered) {
            int column = assignment.first;
            int row = assignment.second;
            if (assigned_[column] != 0 && assigned_[column] != row) {
                inconsistent_ = true;
                return;
            }
            if (assigned_[column] == row) {
                continue;
            }
            if (!Feasible(column, row)) {
                inconsistent_ = true;
                return;
            }
            std::vector<std::pair<int, int>> changes;
            Place(column, row, changes);
        }

        if (!CanonicalStateConsistent()) {
            inconsistent_ = true;
            return;
        }
        if (!StructuralFiltersConsistent()) {
            inconsistent_ = true;
            return;
        }
        if (!DyadicFiltersConsistent()) {
            inconsistent_ = true;
        }
    }
};

std::optional<std::pair<int, int>> ParseAssignment(const std::string& raw, int order) {
    std::size_t separator = raw.find('=');
    if (separator == std::string::npos || separator == 0 || separator == raw.size() - 1) {
        return std::nullopt;
    }

    int column = 0;
    int row = 0;
    try {
        column = std::stoi(raw.substr(0, separator));
        row = std::stoi(raw.substr(separator + 1));
    } catch (const std::exception&) {
        return std::nullopt;
    }
    if (column < 1 || column > order || row < 1 || row > order) {
        return std::nullopt;
    }

    return std::make_pair(column - 1, row);
}

std::optional<std::vector<int>> ParseFocusWidths(const std::string& raw, int order) {
    std::vector<int> widths;
    std::size_t start = 0;
    while (start <= raw.size()) {
        std::size_t end = raw.find(',', start);
        std::string token = raw.substr(start, end == std::string::npos ? std::string::npos : end - start);
        if (token.empty()) {
            return std::nullopt;
        }

        int width = 0;
        try {
            width = std::stoi(token);
        } catch (const std::exception&) {
            return std::nullopt;
        }
        if (width < 1 || width >= order) {
            return std::nullopt;
        }
        if (std::find(widths.begin(), widths.end(), width) == widths.end()) {
            widths.push_back(width);
        }

        if (end == std::string::npos) {
            break;
        }
        start = end + 1;
    }
    return widths;
}

int main(int argc, char* argv[]) {
    if (argc < 3) {
        std::cerr << "usage: costas_native <order> <time_limit_seconds> "
                     "[--focus-widths=w1,w2,...] [column=row ...]\n";
        return 1;
    }

    const int order = std::atoi(argv[1]);
    const double time_limit_seconds = std::atof(argv[2]);
    if (order < 1 || time_limit_seconds <= 0.0) {
        std::cerr << "invalid arguments\n";
        return 1;
    }

    std::vector<std::pair<int, int>> fixed_assignments;
    std::vector<int> focus_widths;
    for (int index = 3; index < argc; ++index) {
        std::string argument = argv[index];
        const std::string focus_prefix = "--focus-widths=";
        if (argument.rfind(focus_prefix, 0) == 0) {
            std::optional<std::vector<int>> parsed =
                ParseFocusWidths(argument.substr(focus_prefix.size()), order);
            if (!parsed.has_value()) {
                std::cerr << "invalid focus widths: " << argv[index] << "\n";
                return 1;
            }
            focus_widths = *parsed;
            continue;
        }

        std::optional<std::pair<int, int>> assignment = ParseAssignment(argv[index], order);
        if (!assignment.has_value()) {
            std::cerr << "invalid assignment: " << argv[index] << "\n";
            return 1;
        }
        fixed_assignments.push_back(*assignment);
    }

    CostasSearcher searcher(order, time_limit_seconds, fixed_assignments, focus_widths);
    const bool found = searcher.Search();

    if (found) {
        std::cout << "status=found\n";
        std::cout << "nodes=" << searcher.nodes() << "\n";
        std::cout << "example=";
        const auto& solution = searcher.solution();
        for (std::size_t index = 0; index < solution.size(); ++index) {
            if (index != 0) {
                std::cout << ' ';
            }
            std::cout << solution[index];
        }
        std::cout << "\n";
        return 0;
    }

    if (searcher.timed_out()) {
        std::cout << "status=unknown\n";
        std::cout << "nodes=" << searcher.nodes() << "\n";
        return 2;
    }

    std::cout << "status=unsat\n";
    std::cout << "nodes=" << searcher.nodes() << "\n";
    return 3;
}
