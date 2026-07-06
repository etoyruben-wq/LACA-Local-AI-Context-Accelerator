#include <algorithm>
#include <cmath>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

struct Point {
    std::string id;
    std::string domain;
    std::string status;
    std::string file;
    double x = 0.0;
    double z = 0.0;
    double y = 0.0;
    double score = 0.0;
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
        std::cerr << "usage: coordinate_ranker <action_points.tsv> <out_state.vmem>\n";
        return 2;
    }
    std::ifstream in(argv[1]);
    if (!in) {
        std::cerr << "cannot open input\n";
        return 1;
    }
    std::string line;
    std::getline(in, line); // header
    std::vector<Point> points;
    while (std::getline(in, line)) {
        auto p = split_tsv(line);
        if (p.size() < 11) continue;
        Point pt;
        pt.id = p[1];
        pt.score = std::stod(p[2]);
        pt.x = std::stod(p[3]);
        pt.z = std::stod(p[4]);
        pt.y = std::stod(p[5]);
        pt.domain = p[6];
        pt.status = p[7];
        pt.file = p[10];
        points.push_back(pt);
    }
    std::sort(points.begin(), points.end(), [](const Point& a, const Point& b) {
        return a.score > b.score;
    });
    std::ofstream out(argv[2]);
    out << "CENTER|FastRank|focus=reranked_points|coord=x,z,y\n";
    int limit = std::min<int>(25, points.size());
    for (int i = 0; i < limit; ++i) {
        const auto& p = points[i];
        out << "POINT|" << p.id
            << "|domain=" << p.domain
            << "|status=" << p.status
            << "|score=" << p.score
            << "|x=" << p.x
            << "|z=" << p.z
            << "|y=" << p.y
            << "|file=" << p.file << "\n";
    }
    out << "NEXT|read_top_points|choose_one_action|write_RESULT.vmem\n";
    std::cout << "wrote " << argv[2] << "\n";
    return 0;
}
