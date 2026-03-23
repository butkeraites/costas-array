#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <iostream>
#include <limits>
#include <string>
#include <utility>
#include <vector>

class CostasSearcher {
  public:
    CostasSearcher(int order, double time_limit_seconds)
        : n_(order),
          assigned_(order, 0),
          row_used_(order + 1, false),
          diff_used_(order, std::vector<char>(2 * order, false)),
          deadline_(std::chrono::steady_clock::now() +
                    std::chrono::milliseconds(static_cast<int>(time_limit_seconds * 1000.0))) {}

    bool Search() { return SearchRecursive(); }

    bool timed_out() const { return timed_out_; }

    long long nodes() const { return nodes_; }

    const std::vector<int>& solution() const { return assigned_; }

  private:
    const int n_;
    std::vector<int> assigned_;
    std::vector<char> row_used_;
    std::vector<std::vector<char>> diff_used_;
    int assigned_count_ = 0;
    long long nodes_ = 0;
    bool timed_out_ = false;
    std::chrono::steady_clock::time_point deadline_;

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

        int column = ChooseColumn();
        if (column < 0) {
            return false;
        }

        std::vector<int> candidates;
        if (!CollectCandidates(column, candidates)) {
            return false;
        }

        OrderCandidates(column, candidates);
        for (int row : candidates) {
            std::vector<std::pair<int, int>> changes;
            Place(column, row, changes);
            if (SearchRecursive()) {
                return true;
            }
            Undo(column, row, changes);
            if (timed_out_) {
                return false;
            }
        }

        return false;
    }

    int ChooseColumn() {
        if (assigned_count_ == 0) {
            return 0;
        }
        if (assigned_[n_ - 1] == 0) {
            return n_ - 1;
        }

        int best_column = -1;
        std::size_t best_domain = std::numeric_limits<std::size_t>::max();
        std::vector<int> candidates;
        for (int column = 0; column < n_; ++column) {
            if (assigned_[column] != 0) {
                continue;
            }
            if (!CollectCandidates(column, candidates)) {
                return -1;
            }
            if (candidates.size() < best_domain) {
                best_domain = candidates.size();
                best_column = column;
            }
        }

        return best_column;
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

    void OrderCandidates(int column, std::vector<int>& candidates) {
        if (column == 0) {
            return;
        }

        int middle = (n_ + 1) / 2;
        std::stable_sort(
            candidates.begin(), candidates.end(),
            [middle](int left, int right) {
                int left_distance = std::abs(left - middle);
                int right_distance = std::abs(right - middle);
                if (left_distance != right_distance) {
                    return left_distance < right_distance;
                }
                return left < right;
            });
    }

    bool Feasible(int column, int row) {
        if (row_used_[row]) {
            return false;
        }
        if (column == 0 && row > (n_ + 1) / 2) {
            return false;
        }
        if (column == n_ - 1 && assigned_[0] != 0 && row <= assigned_[0]) {
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

    void Place(int column, int row, std::vector<std::pair<int, int>>& changes) {
        assigned_[column] = row;
        row_used_[row] = true;
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
        row_used_[row] = false;
        assigned_[column] = 0;
    }
};

int main(int argc, char* argv[]) {
    if (argc != 3) {
        std::cerr << "usage: costas_native <order> <time_limit_seconds>\n";
        return 1;
    }

    const int order = std::atoi(argv[1]);
    const double time_limit_seconds = std::atof(argv[2]);
    if (order < 1 || time_limit_seconds <= 0.0) {
        std::cerr << "invalid arguments\n";
        return 1;
    }

    CostasSearcher searcher(order, time_limit_seconds);
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
