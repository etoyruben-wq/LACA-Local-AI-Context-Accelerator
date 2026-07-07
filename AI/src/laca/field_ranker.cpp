#include <algorithm>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

struct Row {
    std::string id;
    std::string domain;
    std::string status;
    std::string file;
    double score = 0.0;
    double task = 0.0;
    double status_evidence = 0.0;
    double artifact_value = 0.0;
};

static std::vector<std::string> split_tsv(const std::string& line) {
    std::vector<std::string> parts;
    std::stringstream ss(line);
    std::string item;
    while (std::getline(ss, item, '\t')) parts.push_back(item);
    return parts;
}

int main(int argc, char** argv) {
    if (argc < 3) {
        std::cerr << "usage: field_ranker <action_points.tsv> <out_state.vmem>\n";
        return 2;
    }
    std::ifstream in(argv[1]);
    if (!in) {
        std::cerr << "cannot open input\n";
        return 1;
    }
    std::string line;
    std::getline(in, line); // header
    std::vector<Row> rows;
    while (std::getline(in, line)) {
        auto p = split_tsv(line);
        if (p.size() < 11) continue;
        Row r;
        r.id = p[1];
        r.score = std::stod(p[2]);
        r.task = std::stod(p[3]);
        r.status_evidence = std::stod(p[4]);
        r.artifact_value = std::stod(p[5]);
        r.domain = p[6];
        r.status = p[7];
        r.file = p[10];
        rows.push_back(r);
    }
    std::sort(rows.begin(), rows.end(), [](const Row& a, const Row& b) {
        return a.score > b.score;
    });
    std::ofstream out(argv[2]);
    out << "CENTER|FastFieldRank|focus=reranked_points|ranking=bm25f_field\n";
    int limit = std::min<int>(25, rows.size());
    for (int i = 0; i < limit; ++i) {
        const auto& r = rows[i];
        out << "POINT|" << r.id
            << "|domain=" << r.domain
            << "|status=" << r.status
            << "|score=" << r.score
            << "|task=" << r.task
            << "|status_evidence=" << r.status_evidence
            << "|artifact_value=" << r.artifact_value
            << "|file=" << r.file << "\n";
    }
    out << "NEXT|read_top_points|choose_one_action|write_RESULT.vmem\n";
    std::cout << "wrote " << argv[2] << "\n";
    return 0;
}
